"""Structure sizes inside a running server, written to its log on SIGUSR1 (a debugging aid for the soak's creep).
The deep size counts each object once per structure, then once overall (the `excl` column), as inspect_heap.py does.
Also pymalloc's own statistics (how much of what Python holds from the system is free but kept)."""
import functools
import gc
import io
import sys
import time
import types
from collections import OrderedDict, Counter
from contextlib import redirect_stderr


def deep(obj, seen):
    total, stack = 0, [obj]
    while stack:
        o = stack.pop()
        if id(o) in seen or isinstance(o, (type, types.ModuleType, types.FunctionType, types.BuiltinFunctionType)):
            continue
        seen.add(id(o))
        try:
            total += sys.getsizeof(o)
        except TypeError:
            continue
        if isinstance(o, dict):
            for k, v in o.items():
                stack.append(k)
                stack.append(v)
        elif isinstance(o, (list, tuple, set, frozenset)):
            stack.extend(o)
        elif isinstance(o, (str, bytes, int, float, bool, type(None))):
            pass
        else:
            d = getattr(o, "__dict__", None)
            if d is not None:
                stack.append(d)
            for slot in getattr(type(o), "__slots__", ()) or ():
                if hasattr(o, slot):
                    stack.append(getattr(o, slot))
            for name in ("__pydantic_fields_set__", "__pydantic_extra__", "__pydantic_private__"):
                v = getattr(o, name, None)
                if v is not None:
                    stack.append(v)
            if hasattr(o, "_asdict"):
                stack.extend(o)
    return total


def report(label=""):
    from engine import library_cache, memo, web
    t0 = time.time()
    gc.collect()
    MB = 2**20
    rows, whole = [], set()

    def add(name, obj):
        size = deep(obj, set())
        excl = deep(obj, whole)
        rows.append((excl / MB, size / MB, len(obj) if hasattr(obj, "__len__") else None, name))

    for fingerprint, lib in list(library_cache._kept.values()):
        add("library.threads", lib.threads)
        add("library.checked", lib.checked)
        for key, value in list(lib.remembered.items()):
            add(f"library.remembered[{key if not isinstance(key, tuple) else key[0]}]", value)
    try:
        add("answers(remembered)", dict(web._answers))
    except Exception:
        pass
    for attr in ("writers", "flairs"):
        try:
            add(f"profiles.store.{attr}", getattr(web.profiles.store, attr))
        except Exception:
            pass
    live = getattr(web, "live", None)
    if live is not None:
        store = getattr(live, "_store", None)
        add("live checks store", store.__dict__ if store is not None else {})
        add("live checker (rest)", {k: v for k, v in live.__dict__.items() if k != "_store"})
    for name in ("read_ahead", "on_demand"):
        obj = getattr(web, name, None)
        if obj is not None:
            add(f"web.{name}", obj.__dict__)
    seen_ids = set()
    for modname, mod in sorted(sys.modules.items()):
        if not modname.startswith("engine") or mod is None:
            continue
        for name, value in list(vars(mod).items()):
            if id(value) in seen_ids:
                continue
            if isinstance(value, functools._lru_cache_wrapper):
                seen_ids.add(id(value))
                info = value.cache_info()
                if info.currsize:
                    refs = [r for r in gc.get_referents(value) if isinstance(r, (dict, list))]
                    add(f"{modname}.{name} (lru {info.currsize}/{info.maxsize})", refs)
            elif isinstance(value, (dict, OrderedDict, list, set, frozenset)) and not name.startswith("__") and len(value) > 50:
                seen_ids.add(id(value))
                add(f"{modname}.{name}", value)
            elif isinstance(value, (memo.PerList, memo.FileMemo, memo.TypeWindow)):
                seen_ids.add(id(value))
                add(f"{modname}.{name}", value.__dict__)
            elif type(value).__name__ in ("LocalSource", "NameIndex", "KeptLibrary", "ProfileStore", "StoredProfiles"):
                seen_ids.add(id(value))
                add(f"{modname}.{name}", value.__dict__)
    rows.sort(reverse=True)
    out = io.StringIO()
    print(f"=== HEAPDUMP {label} === structures: {sum(r[0] for r in rows):.1f} MB distinct, "
          f"took {time.time() - t0:.0f} s; window saw {len(web._window.kinds)} types, forgot {web._window.forgot}", file=out)
    print(f"{'excl':>7} {'alone':>7} {'n':>9}  structure", file=out)
    for excl, size, n, name in rows[:40]:
        print(f"{excl:7.1f} {size:7.1f} {str(n):>9}  {name}", file=out)
    # all objects by type, bytes (slow, but the whole picture)
    by_type, count = Counter(), Counter()
    for o in gc.get_objects():
        t = type(o).__name__
        count[t] += 1
        try:
            by_type[t] += sys.getsizeof(o)
        except TypeError:
            pass
    print("gc-tracked objects by type (MB, count): " + ", ".join(f"{t} {b / MB:.0f} ({count[t]})" for t, b in by_type.most_common(8)), file=out)
    print(f"strings/bytes are not gc-tracked: sys.getallocatedblocks={sys.getallocatedblocks()}", file=out)
    err = io.StringIO()
    with redirect_stderr(err):
        sys._debugmallocstats()
    keep = [l for l in err.getvalue().splitlines() if l.startswith("# ") or "arenas" in l or l.startswith("Total")]
    print("pymalloc: " + " | ".join(l.strip() for l in keep), file=out)
    return out.getvalue()
