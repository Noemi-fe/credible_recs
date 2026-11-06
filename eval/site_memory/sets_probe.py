"""Who owns the big sets, dicts and lists after the warm answers? usage: run from a tree: python sets_probe.py
Warms like the site (library from data/library), then lists the biggest containers by size with their owner chain
(types and attribute names only, never contents)."""
import gc
import os
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import web  # noqa: E402
from engine.pipeline import cached_profiles  # noqa: E402

web.profiles = cached_profiles()
lib = Path.cwd() / "data" / "library"
t0 = time.time()
web.warm_up(lib)
while web._left_to_warm:
    web.warm_more()
print(f"warmed in {time.time() - t0:.0f} s", flush=True)
gc.collect()
MB = 2**20


def owner(obj, depth=0):
    """A short description of what holds `obj`: attribute of an object, key in a dict of a module, element of a list."""
    out = []
    for ref in gc.get_referrers(obj):
        if ref is sys._getframe() or isinstance(ref, types.FrameType):
            continue
        if isinstance(ref, dict):
            names = [k for k, v in ref.items() if v is obj and isinstance(k, str) and len(k) < 40]
            holder = [r for r in gc.get_referrers(ref) if not isinstance(r, types.FrameType)]
            kind = "module" if any(isinstance(h, types.ModuleType) for h in holder) else "dict"
            mod = next((h.__name__ for h in holder if isinstance(h, types.ModuleType)), "")
            if names:
                out.append(f"{kind} {mod}.{names[0]}")
            elif depth < 2:
                out.append(f"value in a dict of {len(ref)}" + (f" <- {owner(ref, depth + 1)}" if depth < 1 else ""))
        elif isinstance(ref, (list, tuple, set)):
            out.append(f"element of a {type(ref).__name__} of {len(ref)}" + (f" <- {owner(ref, depth + 1)}" if depth < 1 else ""))
        else:
            out.append(f"{type(ref).__name__} object")
        if len(out) >= 2:
            break
    return "; ".join(out) or "?"


rows = []
for o in gc.get_objects():
    if isinstance(o, (set, frozenset, dict, list)):
        try:
            rows.append((sys.getsizeof(o), type(o).__name__, len(o), o))
        except TypeError:
            pass
rows.sort(key=lambda r: -r[0])
by_type = {}
for size, kind, n, _ in rows:
    by_type.setdefault(kind, [0, 0])
    by_type[kind][0] += size
    by_type[kind][1] += 1
print("containers (shell only, MB, count): " + ", ".join(f"{k} {v[0] / MB:.0f} ({v[1]})" for k, v in by_type.items()))
print(f"{'MB':>7} {'kind':>9} {'len':>9}  owner")
for size, kind, n, o in rows[:45]:
    print(f"{size / MB:7.1f} {kind:>9} {n:9}  {owner(o)}"[:260])
# sets by size classes
sets = [r for r in rows if r[1] in ("set", "frozenset")]
buckets = {}
for size, kind, n, o in sets:
    b = "<1KB" if size < 1024 else "<8KB" if size < 8192 else "<64KB" if size < 65536 else "<1MB" if size < MB else ">=1MB"
    buckets.setdefault(b, [0, 0])
    buckets[b][0] += size
    buckets[b][1] += 1
print("sets by size class (MB, count): " + ", ".join(f"{b} {v[0] / MB:.0f} ({v[1]})" for b, v in buckets.items()))
