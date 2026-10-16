"""Latency of the live site (13 Oct 2026): asks the deployed site a fixed set of requests and times each answer, from
outside (what a visitor waits) and as the server reports it (engine/web.py's "timing": its total, and how long it
waited on live checks of quotes against Reddit). Queued is the wait before the server started on the answer: the
network, and a server still getting ready or working out another answer. What's left after the Reddit wait is the
engine's own work, which settings such as the number of processors change; the Reddit wait is what checking quotes
ahead (engine/precheck.py) cuts. eval/latency.py measures the engine on this computer; this measures the site people
use.

    python eval/live_latency.py [--url URL] [--start K] [--limit N] [--repeat]

--start K skips the first K requests of eval/edge_cases/latency_queries.json (to ask ones the server hasn't
remembered) and --limit asks only N of them (each fresh answer can use 20-40 of Reddit's ~200 embed reads per 10
minutes, so a full run of 22 takes a while); --repeat asks each a second time (a remembered answer: the floor). Prints
one line per request and p50 / p95 / max; add the summary to eval/LATENCY.md.
"""

import json
import ssl
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://credible-recs-446702383157.europe-west1.run.app"
QUERIES = ROOT / "eval" / "edge_cases" / "latency_queries.json"


def requests_to_ask() -> list[str]:
    data = json.loads(QUERIES.read_text(encoding="utf-8"))
    items = data.get("queries", data) if isinstance(data, dict) else data
    return [item["text"] if isinstance(item, dict) else item for item in items]


def answer_request_for(url: str, request: str) -> urllib.request.Request:
    """The site's API call for one request: a POST with the request in its JSON body, as the page asks since 16 Oct 2026
    (Noemi's decision 5: never in the address, which Cloud Run's request log keeps)."""
    return urllib.request.Request(f"{url}/api/answer", data=json.dumps({"request": request}).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")


def ask(url: str, request: str) -> dict:
    started = time.perf_counter()
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(answer_request_for(url, request), timeout=600, context=context) as response:
        data = json.load(response)
    timing = data.get("timing") or {}
    total = timing.get("total_s")
    reddit = timing.get("reddit_s")
    waited = round(time.perf_counter() - started, 2)
    return {"request": request, "waited_s": waited, "server_s": total,
            "queued_s": round(waited - total, 2) if total is not None else None, "reddit_s": reddit,
            "engine_s": round(total - reddit, 2) if total is not None and reddit is not None else None,
            "checks": timing.get("checks"), "put_off": timing.get("put_off"),
            "picks": len((data.get("answer") or {}).get("picks", [])),
            "worth": len((data.get("answer") or {}).get("worth_a_look") or [])}


def summary(name: str, values: list[float]) -> str:
    values = sorted(v for v in values if v is not None)
    if not values:
        return f"{name}: none"
    p95 = values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
    return f"{name}: p50 {statistics.median(values):.2f} s, p95 {p95:.2f} s, max {values[-1]:.2f} s"


def main(argv: list[str]) -> int:
    url = argv[argv.index("--url") + 1] if "--url" in argv else DEFAULT_URL
    start = int(argv[argv.index("--start") + 1]) if "--start" in argv else 0
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    requests = requests_to_ask()[start:][:limit]
    rounds = [("fresh", requests)] + ([("repeat", requests)] if "--repeat" in argv else [])
    for label, batch in rounds:
        results = []
        for request in batch:
            result = ask(url, request)
            results.append(result)
            print(f"{label:6} {result['waited_s']:7.2f} s waited | engine {result['engine_s']} s, reddit "
                  f"{result['reddit_s']} s, {result['checks']} checks, queued {result['queued_s']} s | "
                  f"{result['picks']} picks, {result['worth']} worth a look ({result['put_off']} put off) | {request}",
                  flush=True)
        print(summary(f"{label} waited", [r["waited_s"] for r in results]))
        print(summary(f"{label} engine", [r["engine_s"] for r in results]))
        print(summary(f"{label} reddit", [r["reddit_s"] for r in results]))
        if label == "fresh":
            print(summary(f"{label} queued", [r["queued_s"] for r in results]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
