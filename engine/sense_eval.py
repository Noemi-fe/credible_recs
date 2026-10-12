"""The sense evaluation: does every thing an answer shows make sense, for its request, where it is shown?

Noemi's note of 12 Oct 2026, from testing the demo: some recommendations make little sense. "retinol for a beginner with
sensitive skin" showed "Look for: retinol" with a writer saying there's no hurry to start retinol; a pick's quote was a
reply whose "it" only the comment above explained. Every quote passed the word-for-word check; what failed was sense.

What is judged: every item an answer shows (answer_items): each pick's quotes ("pick quote"), its known downsides
("downside") and care tips ("care tip", with the tip's few words), the "What to look for" lines ("look for" and
"avoid", under their kind), the skip-these quotes ("skip") and the care note at the end ("care note").

The criteria. Claude judges each item by hand, reading it as a shopper would: alone, in the answer, under its heading,
for this request. An item makes sense when all three hold:
1. It says what it is about. Its words name the product or kind, or its "it", "this" or "they" can only mean the
   product whose heading it is under (a pick, its downsides, a skipped product, a care tip); and it leans on nothing the
   reader can't see: a reply with no name in it (a "Yes!" and then an "it" never named), a person or
   thing not shown ("for the reasons he said", "the same reaction", "both of them", "that part"), or a product other
   than its heading's that "it" means (a quote shown under one blender whose "it", beating that blender, is another one). Our own words shown with
   it (a care tip's few words, an introduction outside the quotation marks) count as shown. A stray "Yeah," or "Same."
   before a quote that names its product doesn't stop it making sense.
2. It backs what its heading claims. A pick's quote speaks for that product, from use or a clear view: not a passing
   mention ("I have a ballarini"), a look ("This looks very cool!"), or a view of another product (under one rice cooker, a
   quote whose point is that a cheaper brand does as well). A downside states a drawback of the pick; a skipped product's quote warns
   against it. "Look for: X" recommends X: it names X and gives a view of it, not a hedge, a wish or a passing mention;
   "Avoid: X" warns against X and names it. A care tip says how to look after the product.
3. It fits the request. It is about the type of product asked for, as the request means it: "Look for: double
   cleansing" in a sunscreen answer, "Avoid: eye creams" in a moisturiser answer, "Look for: bread knife" for a chef's
   knife or "Look for: pre-ground coffee" for a grinder don't fit. It isn't the requested product itself ("Look for:
   retinol" in a retinol answer is no advice), and it doesn't recommend the opposite of what the request asks ("Look
   for: mineral sunscreen", whose writer warns of a white cast, for a request asking for none).
An item that fails any of the three doesn't make sense. Whether the pick itself is the right product is the ranking's
question, not this one: a quote is judged as what it says under the heading it has.

How it works:
- `python -m engine.sense_eval collect [--jobs N] [--as NAME]` answers each request (sense_requests: the 10 blind-test
  questions and 10 more across skincare, haircare and kitchen; N at a time) on the frozen library snapshot
  (data/eval/library_snapshot, so builders adding threads to the live library don't move the numbers), lists every
  item, saves them in data/eval/sense/items.json and the ones with no verdict yet in data/eval/sense/to_judge.json, and
  prints the report. With `--as NAME` the items are kept as NAME.json instead (items-baseline.json holds the answers
  before the rules of 12 Oct 2026).
- Claude reads to_judge.json and writes a verdict for each item; `python -m engine.sense_eval judge <file>` adds them
  to data/eval/sense/verdicts.json ({key: {"sense": true|false, "why": ...}}). An item's key comes from what a reader
  sees (the request, where it is shown, its heading, our words with it and the quote's text), so a verdict is reused
  for as long as the item is shown the same way, and a changed item (a longer quote, another heading) is judged anew.
- `python -m engine.sense_eval report [NAME]` prints the share of judged items that make sense, and those that don't
  (of the latest collection, or of the one kept as NAME).
- `python -m engine.sense_eval live` checks every collected quote against the comment on Reddit now (engine/
  live_check.py: Reddit's embed page, one comment at a time, kept 48 hours), as answers do before showing a quote.
data/eval/ is git-ignored: the items and verdicts hold Reddit text, so they stay on Noemi's machine. Each answer's
quotes also go through engine.answer.unverified_claims: the count of problems must stay 0.

Answers are written as the demo writes them, with every thread whatever its last live check (with the live checker
on, a thread's age doesn't hold it back), writers' standing from the snapshot's own profile store only, and prices
judged on the day the snapshot was taken (SNAPSHOT_DAY), so the same snapshot always gives the same answers.
"""

import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from engine.answer import AVOID, CARE_NOTE_HEADING, CARE_NOTE_HEADING_ANY, Answer, unverified_claims
from engine.slice_eval import DEFAULT_QUESTIONS

REPO_ROOT = Path(__file__).resolve().parents[1]
SENSE_DIR = REPO_ROOT / "data" / "eval" / "sense"
SNAPSHOT_DIR = REPO_ROOT / "data" / "eval" / "library_snapshot"
SNAPSHOT_DAY = date(2026, 10, 12)  # the day the library snapshot was frozen: its prices are judged on that day
# The ten requests beyond the blind test (12 Oct 2026): skincare, haircare and kitchen, as people type them.
OTHER_REQUESTS = (
    "shampoo for an oily scalp", "anti-dandruff shampoo", "air fryer that lasts", "rice cooker for a family of four",
    "espresso machine for a beginner under £500", "lip balm for very dry lips", "enamelled dutch oven that lasts",
    "conditioner for dry damaged hair", "blender for smoothies", "eye cream for dark circles",
)


@dataclass(frozen=True)
class Item:
    """One thing an answer shows, as a reader sees it."""

    request_id: str  # "b03" (a blind-test question) or "s01" (OTHER_REQUESTS)
    request: str  # the request as typed
    where: str  # "pick quote", "downside", "care tip", "look for", "avoid", "skip" or "care note"
    heading: str  # what it is shown under: the pick's or skipped product's name, the kind, the care note's heading
    lead: str  # our own words shown with it: a care tip's few words, an introduction; "" when none
    text: str  # the quote as shown: the comment's own words, checked word for word
    url: str  # the link to its comment (not part of the key: a reader judges what they read)

    @property
    def key(self) -> str:
        """The item's id: what the reader sees, hashed. The same item shown the same way keeps its verdict."""
        seen = json.dumps([self.request, self.where, self.heading, self.lead, self.text], ensure_ascii=False)
        return hashlib.sha256(seen.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Verdict:
    sense: bool  # True when the item makes sense by the three criteria
    why: str  # which criterion fails and how, in a few words; "" when it makes sense


@dataclass
class Collection:
    items: list[Item] = field(default_factory=list)
    unverified: dict[str, int] = field(default_factory=dict)  # request id -> quotes failing the check (must be 0)
    picks: dict[str, list[str]] = field(default_factory=dict)  # request id -> the picks' names, best first


def sense_requests(questions_path: Path = DEFAULT_QUESTIONS) -> list[tuple[str, str]]:
    """(id, request) for the blind-test questions, then OTHER_REQUESTS as s01 to s10."""
    questions = json.loads(Path(questions_path).read_text(encoding="utf-8"))["questions"]
    return [(q["id"], q["text"]) for q in questions] + [(f"s{n:02d}", text) for n, text in enumerate(OTHER_REQUESTS, 1)]


def answer_items(answer: Answer, request_id: str, request: str) -> list[Item]:
    """Every item the answer shows, in the order a reader meets them."""
    items: list[Item] = []

    def add(where: str, heading: str, quote, lead: str = "") -> None:
        intro = getattr(quote, "intro", "")
        items.append(Item(request_id, request, where, heading, " ".join(w for w in (lead, intro) if w), quote.text,
                          quote.url))

    for pick in answer.picks:
        for quote in pick.quotes:
            add("pick quote", pick.name, quote)
        for quote in pick.downsides:
            add("downside", pick.name, quote)
        for tip in pick.care:
            add("care tip", pick.name, tip.quote, tip.tip)
    for item in answer.look_for:
        add("avoid" if item.advice == AVOID else "look for", item.kind, item.quote)
    for item in answer.skip:
        for quote in item.quotes:
            add("skip", item.name, quote)
    heading = (CARE_NOTE_HEADING.format(product_type=answer.product_type) if answer.product_type
               else CARE_NOTE_HEADING_ANY)
    for tip in answer.care_note:
        add("care note", heading, tip.quote, tip.tip)
    return items


def collect(requests: list[tuple[str, str]], library_dir: Path = SNAPSHOT_DIR, profiles=None,
            today: date = SNAPSHOT_DAY, jobs: int = 1) -> Collection:
    """Each request answered on the library, and every item its answer shows. `profiles`: as in engine.pipeline; with
    `jobs` above 1, the requests are answered that many at a time, each with the library's own profile store
    (snapshot_profiles), and `profiles` isn't used."""
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=jobs) as pool:
            answered = list(pool.map(_answered, requests, [library_dir] * len(requests), [today] * len(requests)))
    else:
        answered = [_answered(request, library_dir, today, profiles) for request in requests]
    found = Collection()
    for (request_id, _), (items, unverified, picks) in zip(requests, answered):
        if items is not None:
            found.items += items
            found.unverified[request_id] = unverified
            found.picks[request_id] = picks
    return found


_SNAPSHOT_PROFILES = object()  # _answered's default: the library's own profile store


def _answered(request: tuple[str, str], library_dir: Path, today: date, profiles=_SNAPSHOT_PROFILES):
    """(items, unverified quotes, picks' names) for one (id, request) answered on the library; (None, 0, []) when module
    1 asks a question or says no."""
    from engine.pipeline import answer_request

    request_id, text = request
    profiles = snapshot_profiles(library_dir) if profiles is _SNAPSHOT_PROFILES else profiles
    run = answer_request(text, library_dir=library_dir, profiles=profiles, today=today, live_check_required=False)
    if run.answer is None:
        return None, 0, []
    return (answer_items(run.answer, request_id, text), len(unverified_claims(run.answer, run.bodies)),
            [pick.name for pick in run.answer.picks])


def snapshot_profiles(library_dir: Path = SNAPSHOT_DIR):
    """Writers' standing from the library's own profile store only (never a call, never the moving cache)."""
    from engine.profiles import ProfileStore, StoredProfiles

    return StoredProfiles(ProfileStore(Path(library_dir) / "profiles.json"))


# --- Verdicts ---

def load_verdicts(path: Path) -> dict[str, Verdict]:
    """{item key: Verdict} from the verdicts file; empty when there is none yet."""
    if not Path(path).exists():
        return {}
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    return {key: Verdict(entry["sense"], entry.get("why", "")) for key, entry in saved.items()}


def add_verdicts(path: Path, judged: dict[str, tuple[bool, str]], items: list[Item]) -> None:
    """Adds verdicts ({item key: (makes sense, why)}) to the file, each saved with the item it judges, so the file
    reads on its own. A key that isn't one of `items` is refused: a verdict must judge something shown."""
    by_key = {item.key: item for item in items}
    unknown = [key for key in judged if key not in by_key]
    if unknown:
        raise ValueError(f"verdicts for items not collected: {', '.join(unknown[:5])}")
    saved = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    for key, (sense, why) in judged.items():
        saved[key] = {"sense": bool(sense), "why": why} | asdict(by_key[key])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def to_judge(items: list[Item], verdicts: dict[str, Verdict]) -> list[Item]:
    """The items with no verdict yet, in order, each once."""
    seen, new = set(), []
    for item in items:
        if item.key not in verdicts and item.key not in seen:
            seen.add(item.key)
            new.append(item)
    return new


def report_lines(items: list[Item], verdicts: dict[str, Verdict]) -> list[str]:
    """The share of judged items that make sense, by where they are shown, then each one that doesn't."""
    judged = [item for item in items if item.key in verdicts]
    sense = [item for item in judged if verdicts[item.key].sense]
    share = f" ({len(sense) / len(judged):.0%})" if judged else ""
    lines = [f"{len(items)} items shown; {len(judged)} judged, {len(sense)} make{'s' if len(sense) == 1 else ''} sense"
             f"{share}; {len(items) - len(judged)} still to judge"]
    totals, good = Counter(item.where for item in judged), Counter(item.where for item in sense)
    lines += [f"  {where}: {good[where]}/{totals[where]}" for where in sorted(totals)]
    for item in judged:
        if not verdicts[item.key].sense:
            lines.append(f"  - {item.request_id} {item.where} ({item.heading}): {verdicts[item.key].why}")
    return lines


# --- Files and the command line ---

def save_collection(found: Collection, folder: Path = SENSE_DIR, name: str = "items") -> None:
    """<name>.json (every item of this collection: "items" for the latest, another name to keep one, such as
    "items-baseline") and to_judge.json (those with no verdict yet)."""
    folder.mkdir(parents=True, exist_ok=True)
    verdicts = load_verdicts(folder / "verdicts.json")
    rows = [asdict(item) | {"key": item.key} for item in found.items]
    (folder / f"{name}.json").write_text(json.dumps({"items": rows, "unverified": found.unverified,
                                                     "picks": found.picks}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    new = [asdict(item) | {"key": item.key} for item in to_judge(found.items, verdicts)]
    (folder / "to_judge.json").write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")


def load_items(folder: Path = SENSE_DIR, name: str = "items") -> list[Item]:
    """The items of a saved collection: by default the latest."""
    rows = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))["items"]
    return [Item(**{k: v for k, v in row.items() if k != "key"}) for row in rows]


def live_lines(items: list[Item], checker) -> list[str]:
    """Each collected quote checked against its comment on Reddit now: how many pass, and which don't."""
    outcomes = {}
    for item in items:
        if (item.url, item.text) not in outcomes:
            outcomes[(item.url, item.text)] = checker.check(item.url, item.text)
    counts = Counter(outcome.status for outcome in outcomes.values())
    lines = [f"{len(outcomes)} quotes checked live: "
             + ", ".join(f"{n} {status}" for status, n in counts.most_common())]
    lines += [f"  - {status.status}: {url}" for (url, _), status in outcomes.items() if status.status != "ok"]
    return lines


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("collect", "judge", "report", "live"):
        print(__doc__)
        return 2
    folder = SENSE_DIR
    options = {flag: argv[argv.index(flag) + 1] for flag in ("--jobs", "--as") if flag in argv}
    rest = [a for i, a in enumerate(argv[1:], 1) if a not in options and argv[i - 1] not in options]
    name = options.get("--as", rest[0] if argv[0] == "report" and rest else "items")
    if argv[0] == "collect":
        library_dir = Path(rest[0]) if rest else SNAPSHOT_DIR
        jobs = int(options.get("--jobs", 1))
        save_collection(collect(sense_requests(), library_dir, snapshot_profiles(library_dir), jobs=jobs), folder, name)
        found = load_items(folder, name)
        unverified = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))["unverified"]
        print(f"Unverified quotes shown: {sum(unverified.values())} (must be 0)")
        print(f"To judge: {len(to_judge(found, load_verdicts(folder / 'verdicts.json')))} items in "
              f"{folder / 'to_judge.json'}")
    elif argv[0] == "judge":
        judged = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        add_verdicts(folder / "verdicts.json", {key: (v["sense"], v.get("why", "")) for key, v in judged.items()},
                     load_items(folder))
    elif argv[0] == "live":
        from engine.live_check import LiveChecker

        print("\n".join(live_lines(load_items(folder), LiveChecker())))
        return 0
    print("\n".join(report_lines(load_items(folder, name), load_verdicts(folder / "verdicts.json"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
