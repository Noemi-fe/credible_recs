"""Answers many requests in one process, as the website would show them, so answers can be read side by side (Noemi,
16 Oct 2026: a breadth-first review of every phase, from request to the page, before testing with interviewees).

Offline: live checks are off (live_check_required=False), so shown quotes are only checked word for word against the
saved comments; nothing reaches Reddit. Every eval request is answered by default (eval/blind_test/questions.json and
eval/edge_cases/*.json but matching.json and retrieval.json), then any request files given (one request a line).

    python eval/sweep.py answer <out.jsonl> [<requests.txt> ...] [--profiles-expired]
        one {"request", "source", "seconds", "json"} a line, "json" being the API's answer (engine.web.answer_json);
        requests already in <out.jsonl> are skipped, so a stopped sweep goes on where it stopped; with
        --profiles-expired (25 Oct 2026) every writer's profile is taken as past its 30 days (engine.profiles.
        as_if_expired), as the library's will be on 9 to 16 Nov
    python eval/sweep.py quoted <out.jsonl> <ids.txt>
        the ids of the comments the answers quote, one a line, no words (for `python -m engine.profiles warm --quoted`)
    python eval/sweep.py view <out.jsonl> [<view.txt>]
        a tester's view of every answer: title, picks (reason, availability, link, image, first quote's start), Also
        worth a look, Skip these, the message
The files hold comments' words (quotes): they stay in docs/ (private) and are deleted within days (the deletion rule).
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIPPED = ("matching.json", "retrieval.json")  # pairs of names, and graded threads: no requests


def eval_requests() -> list[tuple[str, str]]:
    """(request, the file it comes from) for every eval request ("text" of each item), each once."""
    files = [ROOT / "eval/blind_test/questions.json"] + sorted(
        p for p in (ROOT / "eval/edge_cases").glob("*.json") if p.name not in SKIPPED)
    found: dict[str, str] = {}
    for path in files:
        for items in json.loads(path.read_text(encoding="utf-8")).values():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                    found.setdefault(item["text"].strip(), path.stem)
    return list(found.items())


def answer(out: Path, extra: list[Path], profiles_expired: bool = False) -> None:
    from engine.pipeline import answer_request, cached_profiles
    from engine.profiles import as_if_expired
    from engine.web import answer_json
    requests = eval_requests() + [(line.strip(), path.stem) for path in extra
                                  for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = {json.loads(line)["request"] for line in out.read_text(encoding="utf-8").splitlines()} if out.is_file() else set()
    todo = [(r, s) for r, s in dict(requests).items() if r not in done]
    print(f"{len(todo)} requests to answer ({len(done)} done before)", flush=True)
    profiles = as_if_expired(cached_profiles()) if profiles_expired else cached_profiles()
    for i, (request, source) in enumerate(todo, 1):
        started = time.perf_counter()
        try:
            data = answer_json(answer_request(request, profiles=profiles, live_check_required=False))
        except Exception as e:  # one broken answer is reported, the rest go on
            data = {"error": f"{type(e).__name__}: {e}"}
        seconds = round(time.perf_counter() - started, 2)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"request": request, "source": source, "seconds": seconds, "json": data},
                               ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {seconds:6.1f}s {request}", flush=True)


def _quoted_ids(value) -> set[str]:
    """Every "comment_id" anywhere in an answer's JSON (its quotes, downsides, care tips, notes...)."""
    if isinstance(value, dict):
        found = {value["comment_id"]} if isinstance(value.get("comment_id"), str) else set()
        return found.union(*(_quoted_ids(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_quoted_ids(v) for v in value))
    return set()


def quoted(out: Path, listing: Path) -> int:
    """Writes the ids of the comments the sweep's answers quote, one a line (ids only, no words), for `python -m
    engine.profiles warm --quoted` (25 Oct 2026): their writers' profiles are refreshed first. How many."""
    ids: set[str] = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids |= _quoted_ids(json.loads(line).get("json") or {})
    listing.write_text("".join(f"{comment_id}\n" for comment_id in sorted(ids)), encoding="utf-8")
    return len(ids)


def _text(value) -> str:
    """A field's words: itself, or a dict's "text"."""
    if isinstance(value, dict):
        value = value.get("text")
    return value if isinstance(value, str) else ""


def view(out: Path) -> str:
    lines = []
    for row in (json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()):
        data = row["json"]
        lines.append(f"\n=== {row['request']}  [{row['source']}, {row['seconds']}s]")
        if "error" in data:
            lines.append(f"  ERROR {data['error']}")
            continue
        query, ans = data.get("query") or {}, data.get("answer") or {}
        lines.append(f"  understood: {query.get('status')} {query.get('category')} / {query.get('product_type')}"
                     f" ({query.get('department')}) ingredients={query.get('ingredients')} | title: {_text(ans.get('title'))}")
        for said in (query.get("question"), query.get("message")):
            if _text(said):
                lines.append(f"  module 1 says: {_text(said)[:220]}")
        for i, pick in enumerate(ans.get("picks") or [], 1):
            quotes = pick.get("quotes") or []
            lines.append(f"  {i}. {pick.get('name')} | {_text(pick.get('reason'))}")
            lines.append(f"     price: {_text(pick.get('price'))} | availability: {_text(pick.get('availability'))} | "
                         f"link: {'yes' if pick.get('link') else 'no'} | image: {'yes' if pick.get('image') else 'no'}"
                         f" | summary: {_text(pick.get('summary'))[:90]}")
            if pick.get("best_for"):  # 26 Oct 2026, the bestfor builder
                lines.append(f"     best for: {pick['best_for']['text']} ({pick['best_for']['basis']})")
            lines.append(f"     first quote ({len(quotes)}): {_text(quotes[0] if quotes else None)[:140]}")
        worth = [w.get("name") for w in ans.get("worth_a_look") or []]
        skip = [s.get("name") for s in ans.get("skip") or []]
        if worth:
            lines.append(f"  also worth a look: {'; '.join(map(str, worth))}")
        if skip:
            lines.append(f"  skip: {'; '.join(map(str, skip))}")
        if _text(ans.get("message")):
            lines.append(f"  message: {_text(ans.get('message'))[:220]}")
        if data.get("on_demand"):
            lines.append(f"  on demand: {data['on_demand']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "answer":
        expired = "--profiles-expired" in argv
        answer(Path(argv[1]), [Path(a) for a in argv[2:] if a != "--profiles-expired"], expired)
        return 0
    if len(argv) == 3 and argv[0] == "quoted":
        print(f"{quoted(Path(argv[1]), Path(argv[2]))} comments quoted, listed in {argv[2]}")
        return 0
    if len(argv) >= 2 and argv[0] == "view":
        text = view(Path(argv[1]))
        if len(argv) > 2:
            Path(argv[2]).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main(sys.argv[1:]))
