"""The site's memory under load (5 Nov 2026, the site-memory review, DEPLOY.md, The site's memory). The driver runs the
site (serve.py) apart from itself, so a run can be split into segments, each under the heavy lock, with the server stopped
(SIGSTOP) between them. Memory is read with proc_pid_rusage (mem.py) every 0.5 s: the footprint now (phys_footprint, what
jetsam and /usr/bin/time -l count), the lifetime peak footprint (which catches spikes between samples) and the resident set.

  python drive.py start <label> <tree> [--no-model] [--compress]
  python drive.py phase <label> <name> [key=value ...]   names: startup overlap model remembered bundle soak rebundle idle
  python drive.py freeze|dump|stop|report <label>

`dump` makes the server write its structures' sizes to its log (heapdump.py). The dump itself needs memory, so a run that
is measured for its peak is never dumped. Everything a run reads and writes is in the work folder (SITE_MEMORY_WORK,
README.md).
"""
import http.client
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

HERE = Path(__file__).resolve().parent
# Everything a run reads or writes lives in one work folder, outside the repository (it holds commenters' words: the
# library copy, the fake Reddit's pages and the bundles). README.md says how to fill it.
WORK = Path(os.environ.get("SITE_MEMORY_WORK") or HERE.parents[1] / ".cache" / "site_memory")
PY = sys.executable
PORT = 18877
REQ = json.loads((WORK / "requests.json").read_text())


def run_dir(label):
    return WORK / "run" / label


def state(label):
    return json.loads((run_dir(label) / "state.json").read_text())


def save_state(label, data):
    (run_dir(label) / "state.json").write_text(json.dumps(data, indent=1))


class Sampler(threading.Thread):
    def __init__(self, label, pid, phase):
        super().__init__(daemon=True)
        self.label, self.pid, self.phase, self.stop_now = label, pid, phase, False
        self.out = (run_dir(label) / "samples.jsonl").open("a")
        self.max_now = 0.0

    def run(self):
        n = 0
        cache = state(self.label)["cache"]
        while not self.stop_now:
            m = mem.mib(self.pid)
            if m is not None:
                self.max_now = max(self.max_now, m[0])
                row = {"t": round(time.time(), 1), "phase": self.phase, "fp": round(m[0], 1),
                       "peak": round(m[1], 1), "rss": round(m[2], 1)}
                if n % 20 == 0:  # saved checks kept as files: on Cloud Run each takes a 4 KiB page of memory
                    try:
                        row["cache_files"] = len(os.listdir(cache))
                    except OSError:
                        pass
                self.out.write(json.dumps(row) + "\n")
                self.out.flush()
            n += 1
            time.sleep(0.5)


def visitor():
    return f"45.{random.randint(1, 250)}.{random.randint(1, 250)}.{random.randint(1, 250)}"


def post_answer(port, request, region="uk", timeout=400):
    started = time.time()
    body = json.dumps({"request": request, "region": region})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("POST", "/api/answer", body, {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}",
                                                   "X-Forwarded-For": visitor(), "Content-Length": str(len(body))})
        response = conn.getresponse()
        data = response.read()
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = {}
        return response.status, time.time() - started, parsed, len(data)
    except OSError as error:
        return 0, time.time() - started, {"oserror": str(error)}, 0
    finally:
        conn.close()


def ping(port):
    started = time.time()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=400)
    try:
        conn.request("GET", "/ready", headers={"X-Forwarded-For": "35.187.0.1"})
        response = conn.getresponse()
        response.read()
        return response.status, time.time() - started
    except OSError:
        return 0, time.time() - started
    finally:
        conn.close()


def at_once(port, requests, extra_pings=0):
    """All of `requests` posted at the same moment (and `extra_pings` pings beside them)."""
    results = [None] * len(requests)
    pings = []
    barrier = threading.Barrier(len(requests) + extra_pings)

    def one(i):
        barrier.wait()
        results[i] = post_answer(port, requests[i])

    def pinger():
        barrier.wait()
        pings.append(ping(port))

    threads = [threading.Thread(target=one, args=(i,)) for i in range(len(requests))]
    threads += [threading.Thread(target=pinger) for _ in range(extra_pings)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return [{"req": r[:40], "status": s, "s": round(sec, 2), "picks": len(((p.get("answer") or {}).get("picks") or [])),
             "bytes": n} for r, (s, sec, p, n) in zip(requests, results)], pings


def cmd_start(label, tree, flags):
    d = run_dir(label)
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    lib = d / "lib"
    # Hard links: the site only adds files (renamed in). The folder itself is copied, never a link to it (cp -a keeps a
    # symlink as a symlink, and the run would then add its files to the shared copy: it did once, 5 Nov 2026).
    subprocess.run(["cp", "-al", str((WORK / "lib").resolve()), str(lib)], check=True)
    assert lib.is_dir() and not lib.is_symlink(), f"{lib} should be a copy of the library"
    bucket = d / "bucket"
    subprocess.run(["cp", "-R", str(WORK / "cloud" / "bucket"), str(bucket)], check=True)
    cache = d / "cache"
    cache.mkdir()  # empty, as on a new Cloud Run instance: the checks come from the bucket's bundle (load_bundle)
    argv = [PY, str(HERE / "serve.py"), tree, str(PORT), str(cache), str(bucket), str(WORK / "cloud" / "pages"), "--library", str(lib),
            "--reload-seconds", "15"]
    if "--no-model" in flags:
        argv.append("--no-model")
    if "--files" in flags:  # saved checks as files, as the site kept them before 5 Nov 2026
        argv.append("--files")
    if "--compress" in flags:  # a plan looked for and the bundle shared every 60 s, not hourly
        argv += ["--plan-seconds", "60", "--share-seconds", "60"]
    log = (d / "server.log").open("w")
    proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    save_state(label, {"pid": proc.pid, "port": PORT, "tree": tree, "lib": str(lib), "bucket": str(bucket), "cache": str(cache),
                       "started": time.time(), "soak_next": 0, "plan_next": 1, "flags": flags})
    print(f"server {proc.pid} started")


def phase_startup(st, label, **_):
    began = time.time()
    while time.time() - began < 900:
        status, _ = ping(st["port"])
        if status == 200:
            break
        time.sleep(1)
    log = (run_dir(label) / "server.log").read_text()
    return {"ready_after_s": round(time.time() - began, 1), "ready": re.findall(r"Ready for visitors: .*", log),
            "steps": re.findall(r"Getting ready: (.*?) took ([\d.]+) s", log)[:8],
            "left": re.findall(r"Getting ready: left (\d+) requests", log)}


def phase_overlap(st, label, **_):
    """8 cold answers of the biggest product types at once, with a keep-warm ping (read ahead + warm_more) beside them,
    twice; then a third 8 alongside two pings."""
    out = {}
    rows, pings = at_once(st["port"], [r["text"] for r in REQ["big_a"]], extra_pings=1)
    out["round_a"], out["pings_a"] = rows, pings
    rows, pings = at_once(st["port"], [r["text"] for r in REQ["big_b"]], extra_pings=1)
    out["round_b"], out["pings_b"] = rows, pings
    # the refused ones again (busy cap), at once, beside two more pings
    again = [r["req"] for r in out["round_a"] + out["round_b"] if r["status"] != 200]
    full = {r["text"][:40]: r["text"] for r in REQ["big_a"] + REQ["big_b"]}
    retry = [full[k] for k in again][:8]
    if retry:
        rows, pings = at_once(st["port"], retry, extra_pings=2)
        out["retry"], out["pings_retry"] = rows, pings
    log = (run_dir(label) / "server.log").read_text()
    out["warm_more"] = re.findall(r"Getting ready: warmed \d+ more.*", log)[-4:]
    return out


def phase_model(st, label, workers=2, **_):
    todo = list(REQ["model"])
    rows, lock = [], threading.Lock()

    def worker():
        while True:
            with lock:
                if not todo:
                    return
                r = todo.pop(0)
            s, sec, p, n = post_answer(st["port"], r)
            with lock:
                rows.append((r[:30], s, round(sec, 2)))

    ts = [threading.Thread(target=worker) for _ in range(int(workers))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return {"answers": rows}


def phase_remembered(st, label, rounds=4, **_):
    texts = [r["text"] for r in REQ["big_a"] + REQ["big_b"]] + REQ["model"][:16]
    out = []
    for _ in range(int(rounds)):
        rows, _p = at_once(st["port"], texts + texts[:24])  # 64 at once (busy refusals never touch a remembered answer)
        out.append({"statuses": dict((s, sum(1 for r in rows if r["status"] == s)) for s in {r["status"] for r in rows}),
                    "max_s": max(r["s"] for r in rows), "median_s": sorted(r["s"] for r in rows)[len(rows) // 2]})
    return {"rounds": out}


def phase_bundle(st, label, which="biggest", **_):
    """The bundle of the 300 largest library threads (new ids) arrives in the on-demand bucket; the next ping takes it
    into the library folder (all remembered answers forgotten), and 8 cold answers at once read the library again.
    `which`: another bundle file (a typical 300) in place of the largest."""
    src = next((WORK / "bundle_biggest").rglob("threads.json")) if which == "biggest" else Path(which)
    dst = Path(st["bucket"]) / "on_demand" / "threads.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    time.sleep(17)
    p1 = ping(st["port"])
    lib_threads = len(list((Path(st["lib"]) / "threads").glob("*.json")))
    rows, pings = at_once(st["port"], [r["text"] for r in REQ["big_a"]], extra_pings=1)
    rows2, pings2 = at_once(st["port"], [r["text"] for r in REQ["big_b"]], extra_pings=1)
    return {"ping": p1, "threads_in_folder": lib_threads, "after_a": rows, "after_b": rows2, "pings": pings + pings2}


def phase_soak(st, label, minutes=19.0, workers=3, ping_every=3.0, plan_every=240.0, model_every=12, **_):
    """Distinct requests over every product type (the 64-type window turning over all the time), one in `model_every` a
    request the open model reads, `workers` visitors at once; keep-warm pings every `ping_every` s (reading ahead, read
    many times faster than live); a new daily plan with 4,500 other comments to verify every `plan_every` s."""
    soak, model = REQ["soak"], REQ["model"]
    nxt = {"i": st["soak_next"], "plan": st["plan_next"]}
    deadline = time.time() + float(minutes) * 60
    stats = {"200": 0, "503": 0, "429": 0, "other": 0, "s": [], "bytes": 0}
    lock = threading.Lock()
    stop = threading.Event()

    def pinger():
        n = 0
        while not stop.is_set():
            ping(st["port"])
            n += 1
            stop.wait(float(ping_every))
        stats["pings"] = n

    def planner():
        while not stop.wait(float(plan_every)):
            src = WORK / "cloud" / "plans" / f"plan_{nxt['plan']}.json"
            if src.exists():
                shutil.copyfile(src, Path(st["bucket"]) / "live_check" / "plan.json")
                nxt["plan"] += 1

    def worker():
        while time.time() < deadline:
            with lock:
                i = nxt["i"]
                nxt["i"] += 1
            r = model[i % len(model)] + (" please" if i // len(model) % 2 else "") if i % int(model_every) == 0 else soak[i % len(soak)]
            s, sec, p, n = post_answer(st["port"], r)
            with lock:
                key = str(s) if str(s) in stats else "other"
                stats[key] += 1
                if s == 200:
                    stats["s"].append(sec)
                    stats["bytes"] += n

    helpers = [threading.Thread(target=pinger, daemon=True), threading.Thread(target=planner, daemon=True)]
    for t in helpers:
        t.start()
    ws = [threading.Thread(target=worker) for _ in range(int(workers))]
    for t in ws:
        t.start()
    for t in ws:
        t.join()
    stop.set()
    st2 = state(label)
    st2["soak_next"], st2["plan_next"] = nxt["i"], nxt["plan"]
    save_state(label, st2)
    secs = sorted(stats.pop("s"))
    stats.update({"median_s": round(secs[len(secs) // 2], 2) if secs else None,
                  "p90_s": round(secs[int(len(secs) * .9)], 2) if secs else None, "requests_used_to": nxt["i"],
                  "plans_used_to": nxt["plan"] - 1, "cache_files": len(os.listdir(st["cache"]))})
    log = (run_dir(label) / "server.log").read_text()
    stats["reading_ahead"] = re.findall(r"Reading ahead: .*", log)[-3:]
    return stats


def phase_rebundle(st, label, which="biggest", **_):
    """The on-demand bucket's bundle changes again (the reading job added a product) while the site is at its soak
    level: the next due ping downloads and reads the whole bundle again (engine.on_demand.SiteReader.load_threads)."""
    src = next((WORK / f"bundle_{which}").rglob("threads.json")) if which == "biggest" else Path(which)
    dst = Path(st["bucket"]) / "on_demand" / "threads.json"
    shutil.copyfile(src, dst)
    before = mem.mib(st["pid"])
    time.sleep(17)
    p = ping(st["port"])
    time.sleep(2)
    rows, _ = at_once(st["port"], [r["text"] for r in REQ["big_a"]][:4], extra_pings=1)
    after = mem.mib(st["pid"])
    return {"ping": p, "fp_before": round(before[0], 1), "lifetime_peak_before": round(before[1], 1),
            "fp_after": round(after[0], 1), "lifetime_peak_after": round(after[1], 1), "answers": rows}


def phase_idle(st, label, minutes=5.0, ping_every=3.0, **_):
    """Only keep-warm pings, as most of a live day is."""
    deadline = time.time() + float(minutes) * 60
    n = 0
    while time.time() < deadline:
        ping(st["port"])
        n += 1
        time.sleep(float(ping_every))
    return {"pings": n, "cache_files": len(os.listdir(st["cache"]))}


PHASES = {"startup": phase_startup, "overlap": phase_overlap, "model": phase_model, "remembered": phase_remembered,
          "bundle": phase_bundle, "soak": phase_soak, "idle": phase_idle,
          "rebundle": phase_rebundle}


def peaks(label):
    found = {}
    for line in (run_dir(label) / "samples.jsonl").read_text().splitlines():
        row = json.loads(line)
        p = found.setdefault(row["phase"], {"n": 0, "max_fp": 0, "lifetime_peak": 0, "max_rss": 0, "first_fp": row["fp"]})
        p["n"] += 1
        p["max_fp"] = max(p["max_fp"], row["fp"])
        p["lifetime_peak"] = max(p["lifetime_peak"], row["peak"])
        p["max_rss"] = max(p["max_rss"], row["rss"])
        p["last_fp"] = row["fp"]
    return found


def main(argv):
    cmd, label = argv[0], argv[1]
    if cmd == "start":
        cmd_start(label, argv[2], argv[3:])
    elif cmd == "phase":
        name = argv[2]
        options = dict(a.split("=", 1) for a in argv[3:])
        st = state(label)
        os.kill(st["pid"], signal.SIGCONT)
        sampler = Sampler(label, st["pid"], name)
        sampler.start()
        started = time.time()
        try:
            result = PHASES[name](st, label, **options) or {}
        finally:
            time.sleep(3)
            sampler.stop_now = True
            sampler.join(timeout=5)
        result["seconds"] = round(time.time() - started, 1)
        path = run_dir(label) / "results.json"
        allr = json.loads(path.read_text()) if path.exists() else {}
        allr.setdefault(name, []).append(result)
        path.write_text(json.dumps(allr, indent=1))
        print(json.dumps({name: result}, indent=1)[:3000])
        print(json.dumps(peaks(label), indent=1))
    elif cmd == "dump":
        pid = state(label)["pid"]
        log = run_dir(label) / "server.log"
        before = log.read_text().count("=== HEAPDUMP")
        os.kill(pid, signal.SIGCONT)
        os.kill(pid, signal.SIGUSR1)
        waited = 0
        while log.read_text().count("=== HEAPDUMP") <= before and waited < 600:
            time.sleep(2)
            waited += 2
        time.sleep(1)
        text = log.read_text()
        print(text[text.rindex("=== HEAPDUMP"):][:6000])
        os.kill(pid, signal.SIGSTOP)
    elif cmd == "freeze":
        os.kill(state(label)["pid"], signal.SIGSTOP)
    elif cmd == "stop":
        pid = state(label)["pid"]
        try:
            os.kill(pid, signal.SIGCONT)
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(3)
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
    elif cmd == "report":
        print(json.dumps(peaks(label), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
