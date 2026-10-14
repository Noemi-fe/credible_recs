"""Module 2, bulk import: threads chosen from Arctic Shift's per-subreddit history files, for the library.

Noemi's decisions of 14 Oct 2026 (breadth is the priority): bulk history from Arctic Shift's published per-subreddit
files (Academic Torrents' "subreddits23": every post and comment of a subreddit, June 2005 to December 2023), downloaded
after she saw the exact files and sizes. Threads are chosen here, on this machine; only the chosen threads enter the
library (then extracted and slimmed as usual), and the raw files are deleted within 48 hours of the download.

The files: one pair per subreddit, <Sub>_submissions.zst and <Sub>_comments.zst, each a zstandard stream of JSON lines,
one post or comment per line, with Reddit's own field names. They are read as a stream (never unpacked to disk) and
as data only. Only the decided subreddits' files are read (config.SUBREDDITS, as it is when the import runs): another
subreddit's files are named and left unread, so running the import again after Noemi decides one reads them.

Choosing uses modules 1 and 2's own rules; nothing new decides what a good thread is:
1. Which posts. A post whose title names a product type (engine.sources.mentions_product, with module 1's names,
   clues and look-alikes; answers also read a thread whose post alone names it, but the import keeps to the threads
   most likely to be about it: a recipe thread whose post mentions a microwave isn't, 14 Oct 2026), of a kind the
   library mixes (engine.sources.thread_kind: advice, long-term use or a warning), in the type's own subreddits
   (module 1's routing: r/acne only for spot treatments, for example), with real engagement (BULK_MIN_COMMENTS
   comments and a score of BULK_MIN_SCORE), not removed or deleted, not a recurring thread or a general megathread
   ("what's the one gadget..."), not a kitchen thread about food or using the gear (recipes, what to cook, tips) nor one
   about doing without the type, posted from BULK_FIRST_YEAR on, and not already in the library or the gold set. The
   archive saved most posts weeks after they were written, but much of late 2023 within the hour, before their score
   and comment count had settled: for a post saved within a day of its writing, its comments in the file are counted
   instead, and its score isn't asked for.
2. Which types. Module 1's product types as they are when the import runs (engine.query.PRODUCT_TYPES), so a type added
   later is picked up by running it again while the files are still here; `--type "air fryer:kitchen"` adds a type
   module 1 names only through its open model, found by its whole name, as answers find it.
3. How many. Each type aims at BULK_TYPE_TARGET threads about it, split as the library's mix (LIBRARY_MIX: advice 3,
   long-term use 1, warnings 2), and takes only the kinds it is short of, counting what the library already holds: the
   thinnest types and kinds get the most. At most BULK_MAX_NEW_PER_TYPE new threads per type in one run. Each kind
   takes the best posts first, in module 2's graded order (engine.sources.rank_posts, judged as of the files' last day,
   so skincare and haircare threads from the last three years of the files come first), with at most a fair share from
   any one subreddit (engine.sources.choose_mix). A request given with `--request` (need-led choice, Noemi's decision 3
   of 14 Oct 2026: "conditioner for curly hair") first takes up to BULK_PER_REQUEST threads whose title or post talks
   about its needs, ranked for it, whatever its type's cap: the type then counts them. A thread about two types is
   read once and counts for both.

Reading. The chosen threads' comments are collected from the comments files in one pass, and each thread is built as
a thread read from Arctic Shift's API is (engine.arctic_shift.get_thread): the same fields kept, the same rules for
which comments can go in (a reply whose comment isn't there is left out), the same shape (engine.parse_reddit.to_thread),
and read_from "arctic_shift", since the files are Arctic Shift's archive: they may still hold comments people deleted
on Reddit later, so every rule for archive threads applies (live checks, the 37-day retention, each shown quote verified
on Reddit first). Comments are in Reddit's "top" order: each comment, then its replies, best first. Deleted and removed
comments become stubs, as the library keeps them; writers are names only (their flair and the rest are left in the
files). A post's comment count is at least the comments the files hold for it.

Saving. New files only: a thread already in the library, saved by someone else meanwhile say, is never written over.
Each run is logged as `library add` logs its requests (data/library/requests.jsonl: one line per type or request, with
the threads saved), and each thread's provenance (which files, which dump, chosen for what) in data/library/imports.jsonl.
The threads then wait for extraction (`python -m engine.extract todo`), as any new library thread does.

Command line:
    python -m engine.library import-dump <files folder> [--dry-run] [--type "<name>:<category>"]...
                                         [--request "<request>"]... [--requests <file>] [--workers N]
        choose threads in the history files of <files folder> and save them in the library (--dry-run: only say what
        would be chosen); --requests reads one request per line
    python -m engine.bulk_import raw-files <folder>    the raw files still on this machine, and when they must be gone
                                                       (exits 1 while any is left)
    python -m engine.bulk_import delete-raw <folder>   delete them (the history files and the download's part files)
"""

import html
import io
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import config
from engine import query as module_1
from engine.arctic_shift import COMMENT_FIELDS, POST_FIELDS, _connected
from engine.config import (
    BULK_DUMP,
    BULK_DUMP_LAST_DAY,
    BULK_FIRST_YEAR,
    BULK_GENERAL_TYPE_TARGET,
    BULK_MAX_NEW_PER_TYPE,
    BULK_MIN_COMMENTS,
    BULK_MIN_SCORE,
    BULK_PER_REQUEST,
    BULK_RAW_FILES_KEPT_HOURS,
    BULK_TYPE_TARGET,
    LIBRARY_MIX,
)
from engine.gold import DEFAULT_GOLD_DIR, load_threads, unlabelled_gold_ids
from engine.ingredients import ingredient_type_name
from engine.models import Thread
from engine.parse_reddit import REPO_ROOT, category_for, to_thread
from engine.query import ParsedQuery, parse_query
from engine.text import one_edit_apart
from engine.sources import (
    _GONE,
    _RECURRING,
    THREAD_KINDS,
    TYPO_MIN_LENGTH,
    _product_pattern,
    _product_words,
    _title_has,
    choose_mix,
    mentions_product,
    need_words,
    rank_posts,
    thread_kind,
)

DEFAULT_LIBRARY_DIR = REPO_ROOT / "data" / "library"
FILE_NAME = re.compile(r"^(?P<subreddit>[A-Za-z0-9_]+)_(?P<part>submissions|comments)\.zst$")
# The download's own part files (pieces of files next to the chosen ones) are raw files too.
RAW_PATTERNS = ("*_submissions.zst", "*_comments.zst", ".*.parts")
LAST_DAY = datetime.fromisoformat(BULK_DUMP_LAST_DAY).replace(hour=23, minute=59, second=59, tzinfo=UTC)
SETTLED_AFTER = timedelta(days=1)  # the archive saved a post this long after its writing: its numbers had settled
WORKERS = 4  # files read at once (each by a process of its own)
_LINK_ID = re.compile(r'"link_id"\s*:\s*"t3_([A-Za-z0-9_]+)"')  # found before a comment's line is read as JSON
UK = ZoneInfo("Europe/London")


# --- Reading the files ---

def read_lines(path: Path) -> Iterator[str]:
    """The lines of one history file, read as a stream: zstandard with a large window (these files need up to 2 GB)."""
    import zstandard  # only the import needs it (pyproject's "dumps" extra)

    with Path(path).open("rb") as raw:
        reader = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(raw, read_size=2**20)
        yield from io.TextIOWrapper(reader, encoding="utf-8", errors="replace")


def history_files(folder: Path) -> tuple[dict[str, dict[str, Path]], list[str]]:
    """{subreddit: {"submissions": file, "comments": file}} for the decided subreddits' files in the folder, and the names
    of the files left unread because their subreddit isn't a decided one (config.SUBREDDITS), sorted."""
    found: dict[str, dict[str, Path]] = {}
    skipped = []
    for path in sorted(Path(folder).iterdir()):
        name = FILE_NAME.match(path.name)
        if not name or not path.is_file():
            continue
        if not categories_of(name["subreddit"]):
            skipped.append(path.name)
            continue
        found.setdefault(name["subreddit"], {})[name["part"]] = path
    return found, sorted(skipped)


def categories_of(subreddit: str) -> tuple[str, ...]:
    """The categories a subreddit is decided for, in config.THREAD_CATEGORIES' order: one for most, two or more for a
    community shared by categories (r/BuyItForLife is the kitchen's and the general category's, 14 Oct 2026)."""
    name = subreddit.strip().removeprefix("r/").lower()
    return tuple(c for c in config.THREAD_CATEGORIES if name in {s.lower() for s in config.SUBREDDITS.get(c, ())})


def _number(value) -> int | None:
    """A whole number from the files, which write some as text ("1382415688"); None when there is none."""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _post_fields(record: dict) -> dict | None:
    """What a post keeps (engine.arctic_shift.POST_FIELDS, as a thread read from the API keeps), its id without Reddit's
    prefix and its numbers as numbers; None for a post with no id, title or date."""
    post = {name: record.get(name) for name in POST_FIELDS}
    post["id"] = str(record.get("id") or "").removeprefix("t3_")
    post["created_utc"] = _number(record.get("created_utc"))
    post["score"] = _number(record.get("score")) or 0
    post["num_comments"] = max(0, _number(record.get("num_comments")) or 0)
    post["removed_by_category"] = record.get("removed_by_category")
    if not post["id"] or not str(post.get("title") or "").strip() or post["created_utc"] is None:
        return None
    return post


def _settled(record: dict) -> bool:
    """Whether the archive saved the post long enough after its writing for its score and comment count to have settled.
    A post with no saving time is taken as it is."""
    saved = [n for n in (_number(record.get("retrieved_on")), _number(record.get("retrieved_utc"))) if n is not None]
    created = _number(record.get("created_utc"))
    return not saved or created is None or max(saved) - created >= SETTLED_AFTER.total_seconds()


def _names(title: str, body: str, subject: str, title_words: set[str] | None = None) -> bool:
    """Whether a post's title or text names the subject (a product type, or an ingredient's type), as answers judge a
    thread (engine.pipeline._about_the_product). The text is read only when it holds one of the subject's words exactly.

    For speed, the full check (engine.sources.mentions_product) runs only where it can say yes: on a title holding one of
    the subject's words, or a long word one letter from one of its long names (`title_words`: the title's long words,
    worked out once per post: _long_words)."""
    if _product_pattern(subject).search(title) or _could_be_a_slip(title_words or _long_words(title), subject):
        if mentions_product(title, subject):
            return True
    return bool(body) and bool(_product_pattern(subject).search(body)) and mentions_product(body, subject)


def _titled(title: str, subject: str, title_words: set[str]) -> bool:
    """Whether the title names the subject, as engine.sources.mentions_product reads it; for speed, the full check runs
    only where it can say yes (_names)."""
    if _product_pattern(subject).search(title) or _could_be_a_slip(title_words, subject):
        return mentions_product(title, subject)
    return False


# Kitchen threads about food or about using the gear, not about choosing it, are left out (14 Oct 2026, the coordinator's
# rule after the first import: several of the biggest threads chosen were these): recipes ("favourite Instant Pot
# recipes?", which module 2 ranks low too: engine.sources._CARE), what to cook, make or add, meal and dish ideas, the
# best thing someone cooked in it, tips for getting the most out of it, and "I made a milkshake in my food processor".
# Buying tips ("tips for buying a rice cooker") and care questions ("how do I season my wok") stay.
_FOOD_OR_USE = re.compile(
    r"\b(recipes?"
    r"|what\b(\s+\w+){0,4}\s+(can|should|could|do) (i|we|you) (make|cook|bake|do with)"
    r"|what (can|should) (i|we) add\b.{0,40}\bto make"
    r"|what to (make|cook|bake)"
    r"|best thing (you|to|i)('ve)? (cook|make|bake|made|cooked|baked)"
    r"|(meal|dinner|dish|snack|breakfast|lunch) (ideas?|prep)|ideas? for (meals?|dinner|dishes)"
    r"|(thanksgiving|christmas|holiday|party|potluck|weeknight|side|favou?rite|easy|quick|healthy|cheap) (dish(es)?|meals?)"
    r"|dish(es)? (ideas?|to (make|bring))"
    r"|(best|any|your) tips? (for|on|to) (getting the most|using|use|cooking)|best tip ever"
    r"|i (just )?made (a|an|some|this|my)|(buy|get) to (cook|make|eat)|infuse)\b",
    re.IGNORECASE)

# General megathreads ("what's the one kitchen gadget you'd buy again?", "what cooking tool was a waste of money?") name
# a type only in passing: their thousands of comments are about everything else. Left out in every category.
_MEGATHREAD = re.compile(
    r"\bwhat('?s| is| was| are| were)?\s+(is\s+)?(the|your)\s+(one|single|best|worst|favou?rite|most\s+\w+)\b"
    r".{0,40}?\b(items?|things?|tools?|gadgets?|appliances?|purchases?)\b"
    r"|\bwhat\s+(cooking\s+|kitchen\s+)?(tools?|items?|gadgets?|appliances?|things?)\s+"
    r"(was|were|is|are|do|did|have|has|would|should)\b",
    re.IGNORECASE)

_WITHOUT = re.compile(r"\bwithout (using )?(a|an|my|the)\s+", re.IGNORECASE)


def _without(title: str, subject: str) -> bool:
    """Whether the title asks about doing without the subject ("rice without a rice cooker"): a thread about its
    absence isn't about choosing one."""
    pattern = _product_pattern(subject)
    return any(pattern.match(title, found.end()) for found in _WITHOUT.finditer(title))


def _long_words(text: str) -> set[str]:
    """The words engine.sources.mentions_product forgives a slip in (as long as its long names, but one letter), each
    without a plural "s", as it reads them."""
    return {w.removesuffix("s") for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= TYPO_MIN_LENGTH - 1}


def _could_be_a_slip(words: set[str], subject: str) -> bool:
    long_names = [w for w in _product_words(subject) if " " not in w and len(w) >= TYPO_MIN_LENGTH]
    return any(one_edit_apart(word, name) for word in words for name in long_names)


def _gone(post: dict) -> bool:
    """A post removed or deleted, as module 2's ranking leaves out (engine.sources.rank_posts)."""
    return (str(post.get("title") or "").strip().lower() in _GONE or bool(post.get("removed_by_category"))
            or str(post.get("selftext") or "").strip() in _GONE)


def scan_submissions(path: str, subjects: tuple[tuple[str, str], ...], first_year: int = BULK_FIRST_YEAR,
                     min_comments: int = BULK_MIN_COMMENTS, min_score: int = BULK_MIN_SCORE) -> tuple[list[dict], dict]:
    """The candidate posts of one submissions file, and how many posts each reason left out.

    A candidate names one of `subjects` ((category, subject) pairs: a product type, or an ingredient's type, with its
    category, whose words judge its kind) in its title, is of a kind the library mixes for it, isn't removed, deleted,
    recurring, a megathread or a kitchen food or usage thread, was posted from `first_year` to the files' last day, and has real engagement, unless its
    numbers hadn't settled when the archive saved it (then its comments are counted later). Each candidate keeps
    POST_FIELDS, "about" (the subjects it names, each with its kind), "settled", and "file" and "source" (the file and
    the subreddit as its name writes it)."""
    categories = tuple(dict.fromkeys(category for category, _ in subjects))
    kept, left_out = [], Counter()
    first = datetime(first_year, 1, 1, tzinfo=UTC).timestamp()
    for line in read_lines(Path(path)):
        try:
            record = json.loads(line)
        except ValueError:
            left_out["unreadable line"] += 1
            continue
        post = _post_fields(record) if isinstance(record, dict) else None
        if post is None or _gone(post):
            left_out["removed, deleted or empty"] += 1
            continue
        if not first <= post["created_utc"] <= LAST_DAY.timestamp():
            left_out[f"posted before {first_year}"] += 1
            continue
        # The files write "&" as "&amp;" (Reddit's HTML codes), whose letters name nothing ("amp" isn't a guitar amp):
        # the post is judged as it reads, and kept as the files write it, as the library keeps every thread.
        readable = post | {"title": html.unescape(str(post["title"])),
                           "selftext": html.unescape(str(post.get("selftext") or ""))}
        title = readable["title"]
        if _RECURRING.search(title.lower()):
            left_out["a recurring thread"] += 1
            continue
        if _MEGATHREAD.search(title):
            left_out["a general megathread"] += 1
            continue
        # Cheap and exact first: a title of no kind at all is of no kind for any type (a warning needs its words too),
        # and engagement doesn't depend on the type.
        if not any(thread_kind(readable, category) in THREAD_KINDS for category in categories):
            left_out["of no kind the library mixes"] += 1
            continue
        settled = _settled(record)
        if settled and (post["num_comments"] < min_comments or post["score"] < min_score):
            left_out["too little engagement"] += 1
            continue
        kinds, title_words = {}, _long_words(title)
        for category, subject in subjects:
            if (category == "kitchen" and _FOOD_OR_USE.search(title)) or _without(title, subject):
                continue
            if subject not in kinds and _titled(title, subject, title_words):
                kind = thread_kind(readable, category, subject)
                if kind in THREAD_KINDS:
                    kinds[subject] = kind
        if not kinds:
            left_out["about no product type, or of no kind the library mixes for it"] += 1
            continue
        kept.append(post | {"about": kinds, "settled": settled, "file": Path(path).name,
                            "source": FILE_NAME.match(Path(path).name)["subreddit"]})
    return kept, dict(left_out)


def count_comments(path: str, post_ids: Iterable[str]) -> dict[str, int]:
    """{post id: comments the file holds for it}, for the given posts."""
    wanted, counts = set(post_ids), Counter()
    for line in read_lines(Path(path)):
        found = _LINK_ID.search(line)
        if found and found.group(1) in wanted:
            counts[found.group(1)] += 1
    return dict(counts)


def collect_comments(path: str, post_ids: Iterable[str]) -> dict[str, list[dict]]:
    """{post id: its comments in the file}, for the given posts, each keeping only COMMENT_FIELDS (as a thread read from
    the API keeps), its id without Reddit's prefix and its date and score as numbers."""
    wanted, comments = set(post_ids), {}
    for line in read_lines(Path(path)):
        found = _LINK_ID.search(line)
        if not found or found.group(1) not in wanted:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        comments.setdefault(found.group(1), []).append(_comment_fields(record))
    return comments


def _comment_fields(record: dict) -> dict:
    comment = {name: record.get(name) for name in COMMENT_FIELDS}
    comment["id"] = str(record.get("id") or "").removeprefix("t1_")
    comment["created_utc"] = _number(record.get("created_utc"))
    comment["score"] = _number(record.get("score")) or 0
    return comment


def _run_all(function, jobs: list[tuple], workers: int) -> list:
    """function(*job) for every job, in order: in processes of their own when `workers` > 1."""
    if workers <= 1 or len(jobs) <= 1:
        return [function(*job) for job in jobs]
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
        return list(pool.map(function, *zip(*jobs)))


# --- Building a thread ---

def build_thread(post: dict, comments: list[dict], read_at: datetime, category: str | None = None) -> Thread:
    """The thread of a post and its comments from the files, in the shape of a thread read from Arctic Shift's API
    (read_from "arctic_shift", never checked live): see the module's docstring. `category`: the category of what it was
    chosen for, which a community decided for several categories takes (engine.sources.for_request); by default its
    community's first, as the API's reader names it."""
    post_id = post["id"]
    kept = _in_reddit_order(_connected([_comment_fields(c) for c in comments], post_id), post_id)
    fields = {name: post.get(name) for name in POST_FIELDS} | {"id": post_id}
    fields["num_comments"] = max(post.get("num_comments") or 0, len(kept))
    return to_thread({"post": fields, "comments": kept}, category or category_for(str(post["subreddit"])), read_at,
                     read_from="arctic_shift")


def _in_reddit_order(comments: list[dict], post_id: str) -> list[dict]:
    """Each comment, then its replies, best first: Reddit's "top" order, which Parse reads threads in (siblings by score,
    then the older first)."""
    replies: dict[str, list[dict]] = {}
    for c in comments:
        parent = str(c.get("parent_id") or "")
        plain = parent.removeprefix("t1_").removeprefix("t3_")
        replies.setdefault("" if not parent or parent.startswith("t3_") or plain == post_id else plain, []).append(c)
    for siblings in replies.values():
        siblings.sort(key=lambda c: (-(c.get("score") or 0), c.get("created_utc") or 0, c["id"]))
    ordered, seen, pending = [], set(), list(reversed(replies.get("", [])))
    while pending:
        comment = pending.pop()
        if comment["id"] in seen:
            continue
        seen.add(comment["id"])
        ordered.append(comment)
        pending += reversed(replies.get(comment["id"], []))
    return ordered


def save_new(thread: Thread, threads_dir: Path, never: Iterable[str] = ()) -> bool:
    """Writes the library's copy of the thread (engine.library: deleted and removed comments as stubs) as a new file;
    False, writing nothing, when the file is already there or the thread is one that never enters the library (a gold
    thread, `never`). Written to a temporary file first and linked into place, which fails if a file appeared."""
    from engine.library import _library_copy  # here: engine.library imports this module for its command

    if thread.id in set(never):
        return False
    threads_dir = Path(threads_dir)
    threads_dir.mkdir(parents=True, exist_ok=True)
    path = threads_dir / f"{thread.id}.json"
    if path.exists():
        return False
    temporary = threads_dir / f".{thread.id}.import"
    temporary.write_text(_library_copy(thread).model_dump_json(indent=2) + "\n", encoding="utf-8")
    try:
        os.link(temporary, path)
    except FileExistsError:
        return False
    finally:
        temporary.unlink(missing_ok=True)
    return True


# --- Choosing ---

@dataclass
class TypePlan:
    name: str  # the product type
    category: str
    have: dict[str, int]  # threads about it already in the library, by kind
    found: dict[str, int] = field(default_factory=dict)  # candidates in the files, by kind
    chosen: list[dict] = field(default_factory=list)  # new threads about it, best first, each with its "kind" for it


@dataclass
class RequestPlan:
    request: str  # as typed
    status: str  # module 1's outcome
    product_type: str | None = None
    found: int = 0  # candidates talking about its needs
    chosen: list[dict] = field(default_factory=list)


@dataclass
class ImportResult:
    dry_run: bool
    types: list[TypePlan] = field(default_factory=list)
    requests: list[RequestPlan] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)  # not a decided subreddit's: left unread
    missing_comments: list[str] = field(default_factory=list)  # subreddits whose comments file isn't there
    posts_read: int = 0  # candidates found before engagement was counted and the library's threads left out
    left_out: dict[str, int] = field(default_factory=dict)  # posts left out, by reason
    chosen: dict[str, dict] = field(default_factory=dict)  # every new thread chosen: post id -> post, in choosing order
    saved: list[str] = field(default_factory=list)  # new thread files written
    already_there: list[str] = field(default_factory=list)  # chosen, but a file appeared meanwhile: left as it was
    comments_saved: int = 0
    problems: list[str] = field(default_factory=list)

    def type_plan(self, name: str) -> TypePlan:
        return next(plan for plan in self.types if plan.name == name)


def type_queries(extra_types: Iterable[tuple[str, str]] = (), problems: list[str] | None = None) -> list[ParsedQuery]:
    """The product types to choose threads for: module 1's, as they are now, each read as module 1 reads its name, then
    the extra ones, each a type of its own read from its category's decided subreddits (as the open model's are)."""
    queries, names = [], set()
    for product in module_1.PRODUCT_TYPES:
        parsed = parse_query(product.name, model=None)
        if parsed.status == "ok" and parsed.product_type == product.name:
            queries.append(parsed)
            names.add(product.name)
        elif problems is not None:
            problems.append(f"module 1 doesn't read {product.name!r} as itself; no threads chosen for it")
    for name, category in extra_types:
        name = " ".join(name.lower().split())
        if name in names:
            continue
        names.add(name)
        queries.append(ParsedQuery(text=name, status="ok", category=category, product_type=name, search_terms=[name],
                                   subreddits=list(config.SUBREDDITS[category])))
    return queries


def _subjects(query: ParsedQuery) -> list[str]:
    """What a post must name to be about the request: its product type, or an active ingredient it names."""
    found = [query.product_type]
    if query.constraints.ingredients:
        found.append(ingredient_type_name(query.constraints.ingredients))
    return found


def _kind_targets(total: int) -> dict[str, int]:
    """`total` threads split as the library's mix (largest remainders), e.g. 36: 18 advice, 6 long-term use, 12 warnings."""
    weights = {kind: LIBRARY_MIX.get(kind, 0) for kind in THREAD_KINDS}
    whole = sum(weights.values()) or 1
    shares = {kind: total * weight // whole for kind, weight in weights.items()}
    rest = sorted(THREAD_KINDS, key=lambda kind: (-(total * weights[kind] % whole), THREAD_KINDS.index(kind)))
    for kind in rest[:total - sum(shares.values())]:
        shares[kind] += 1
    return shares


def _have(threads: list[Thread], name: str, category: str) -> dict[str, int]:
    """The library's threads about a type (title or post names it), by kind."""
    counts = Counter()
    for thread in threads:
        if thread.category == category and _names(html.unescape(thread.title), html.unescape(thread.body or ""), name):
            kind = thread_kind({"title": thread.title}, category, name)
            if kind in THREAD_KINDS:
                counts[kind] += 1
    return {kind: counts[kind] for kind in THREAD_KINDS}


def _kind_for(post: dict, query: ParsedQuery) -> str | None:
    """The post's kind for the request: for its type, else for an ingredient it names."""
    return next((post["about"][s] for s in _subjects(query) if s in post["about"]), None)


def _candidates(posts: list[dict], query: ParsedQuery) -> list[dict]:
    """The posts that can be chosen for the request: in its subreddits, about it, of a kind the library mixes."""
    subreddits = {s.lower() for s in query.subreddits}
    return [p for p in posts if str(p["subreddit"]).lower() in subreddits and _kind_for(p, query)]


def _talks_about_needs(post: dict, needs: list[str]) -> bool:
    texts = (str(post["title"]).lower(), str(post.get("selftext") or "").lower())
    return not needs or any(_title_has(text, word) for text in texts for word in needs)


def _ranked(query: ParsedQuery, posts: list[dict]) -> list[dict]:
    """Module 2's graded order (engine.sources.rank_posts), judged as of the files' last day."""
    return rank_posts(query, posts, now=LAST_DAY)


def _choose_for_request(plan: RequestPlan, query: ParsedQuery, posts: list[dict], chosen: dict[str, dict]) -> None:
    """Up to BULK_PER_REQUEST threads talking about the request's needs, ranked for it, as a mix of kinds; its type's
    cap doesn't limit them (two requests about shampoo each get theirs), but counts them afterwards."""
    needs = need_words(query)
    pool = [p for p in _candidates(posts, query) if _talks_about_needs(p, needs)]
    plan.found = len(pool)
    total = BULK_PER_REQUEST
    fresh = [p for p in pool if p["id"] not in chosen]
    picked = choose_mix(query, _ranked(query, fresh), total=total, mix=_kind_targets(total), fill=True) if total else []
    for post in picked:
        post.setdefault("category", query.category)
        chosen[post["id"]] = post
    plan.chosen = [p | {"kind": _kind_for(p, query)} for p in picked]


def _choose_for_type(plan: TypePlan, query: ParsedQuery, posts: list[dict], chosen: dict[str, dict]) -> None:
    """The kinds the type is short of, best first, within its cap; threads already chosen for another type or a request
    that are about this one count for it."""
    name = plan.name
    candidates = _candidates(posts, query)
    plan.found = {kind: sum(p["about"][name] == kind for p in candidates if name in p["about"]) for kind in THREAD_KINDS}
    already = [p for p in chosen.values() if name in p["about"]]
    have = Counter(plan.have) + Counter(p["about"][name] for p in already)
    target = BULK_GENERAL_TYPE_TARGET if plan.category == "general" else BULK_TYPE_TARGET
    shares = {kind: max(0, aim - have[kind]) for kind, aim in _kind_targets(target).items()}
    total = min(max(0, BULK_MAX_NEW_PER_TYPE - len(already)), sum(shares.values()))
    fresh = [p for p in candidates if p["id"] not in chosen and name in p["about"]]
    picked = choose_mix(query, _ranked(query, fresh), total=total, mix=shares, fill=False) if total else []
    for post in picked:
        post.setdefault("category", query.category)
        chosen[post["id"]] = post
    plan.chosen = [p | {"kind": p["about"][name]} for p in already + picked]


def _saved_category(post: dict, category_of: dict[str, str]) -> str:
    """The category a chosen thread is saved in, which the answers that read it are of (engine.sources.LocalSource reads
    a request's category only): its types' category. A thread about types of two categories, from a community they
    share (r/BuyItForLife's "Which gloves last for working in a freezer?": a freezer and gloves), is saved in the one
    module 1 reads in its title, as a request typed so would be answered; when module 1 reads none of them there, in
    the community's own (the first decided for it, as a reader names it: engine.parse_reddit.category_for), not in
    whichever chose it first (the thinnest types choose first)."""
    found = {category_of[subject] for subject in post["about"] if subject in category_of}
    if len(found) == 1:
        return found.pop()
    if len(found) > 1:
        reading = parse_query(html.unescape(str(post["title"])), model=None)
        if reading.status == "ok" and reading.category in found:
            return reading.category
        own = category_for(str(post["subreddit"]))
        if own in found:
            return own
    return post["category"]


# --- The whole import ---

def import_dump(files_dir: Path, library_dir: Path = DEFAULT_LIBRARY_DIR, requests: Iterable[str] = (),
                extra_types: Iterable[tuple[str, str]] = (), dry_run: bool = False, now: datetime | None = None,
                never: Iterable[str] | None = None, workers: int = WORKERS) -> ImportResult:
    """Chooses threads in the history files of `files_dir`, then (unless `dry_run`) reads and saves them in the library.

    `requests`: requests to choose need-led threads for, as typed. `extra_types`: (name, category) pairs of types module
    1 names only through its open model. `never`: thread ids that never enter the library (by default the gold set's
    threads, labelled or not: a labelled one's copy comes from the gold set). `now`: when the threads are read, their
    collected_at."""
    now = now or datetime.now(UTC)
    result = ImportResult(dry_run=dry_run)
    files, result.skipped_files = history_files(Path(files_dir))
    threads_dir = Path(library_dir) / "threads"
    saved_ids = {path.stem for path in threads_dir.glob("*.json")} if threads_dir.is_dir() else set()
    library_threads = load_threads(threads_dir, skip_broken=True) if threads_dir.is_dir() else []
    never = _gold_ids() if never is None else set(never)

    types = type_queries(extra_types, result.problems)
    asked = []
    for text in requests:
        parsed = parse_query(text)
        asked.append((RequestPlan(text, parsed.status, parsed.product_type), parsed))
        if parsed.status != "ok":
            result.problems.append(f"{text!r}: module 1 can't place it ({parsed.status}); no threads chosen for it")
    queries = types + [parsed for _, parsed in asked if parsed.status == "ok"]
    subjects = {category: tuple(dict.fromkeys(s for q in queries if q.category == category for s in _subjects(q)))
                for category in config.THREAD_CATEGORIES}

    jobs = [(str(paths["submissions"]), tuple((c, s) for c in categories_of(sub) for s in subjects.get(c, ())))
            for sub, paths in files.items() if "submissions" in paths]
    posts, left_out = [], Counter()
    for found, counts in _run_all(scan_submissions, jobs, workers):
        posts += found
        left_out.update(counts)
    result.files_read = [Path(job[0]).name for job in jobs]
    result.posts_read = len(posts)
    known = len(posts)
    posts = [p for p in posts if p["id"] not in saved_ids and p["id"] not in never]
    left_out["already in the library or the gold set"] += known - len(posts)
    _settle(posts, files, workers, left_out, result)
    posts = [p for p in posts if p["num_comments"] >= BULK_MIN_COMMENTS]
    result.left_out = dict(left_out)

    chosen: dict[str, dict] = {}
    for plan, parsed in asked:
        if parsed.status == "ok":
            _choose_for_request(plan, parsed, posts, chosen)
    result.requests = [plan for plan, _ in asked]
    plans = [(TypePlan(q.product_type, q.category, _have(library_threads, q.product_type, q.category)), q) for q in types]
    for plan, parsed in sorted(plans, key=lambda pair: sum(pair[0].have.values())):  # the thinnest first
        _choose_for_type(plan, parsed, posts, chosen)
    category_of = {subject: category for category, found in subjects.items() for subject in found}
    for post in chosen.values():
        post["category"] = _saved_category(post, category_of)
    result.types = [plan for plan, _ in plans]
    result.chosen = chosen
    if not dry_run:
        carry_out(result, files_dir, library_dir, now, never, workers)
    return result


def carry_out(result: ImportResult, files_dir: Path, library_dir: Path = DEFAULT_LIBRARY_DIR,
              now: datetime | None = None, never: Iterable[str] | None = None, workers: int = WORKERS) -> ImportResult:
    """Reads and saves the threads a run chose (a dry run's, say, once looked over), and logs them; returns the result,
    now saying what was saved."""
    now = now or datetime.now(UTC)
    never = _gold_ids() if never is None else set(never)
    result.dry_run = False
    if result.chosen:
        files, _ = history_files(Path(files_dir))
        _read_and_save(result.chosen, files, Path(library_dir) / "threads", never, now, workers, result)
        _log(result, result.chosen, Path(library_dir), now)
    return result


def _gold_ids() -> set[str]:
    """Every gold-set thread: the unlabelled ones never enter the library, and a labelled one's copy comes from the gold
    set itself (CLAUDE.md), never from the files."""
    gold = DEFAULT_GOLD_DIR / "threads"
    return unlabelled_gold_ids() | ({path.stem for path in gold.glob("*.json")} if gold.is_dir() else set())


def _settle(posts: list[dict], files: dict, workers: int, left_out: Counter, result: ImportResult) -> None:
    """For the posts whose numbers hadn't settled, their comments in the file are their count."""
    unsettled: dict[str, list[dict]] = {}
    for post in posts:
        if not post["settled"]:
            unsettled.setdefault(post["source"], []).append(post)
    jobs = [(str(files[sub]["comments"]), [p["id"] for p in waiting]) for sub, waiting in unsettled.items()
            if "comments" in files.get(sub, {})]
    counted: dict[str, int] = {}
    for counts in _run_all(count_comments, jobs, workers):
        counted.update(counts)
    for post in posts:
        if not post["settled"]:
            post["num_comments"] = max(post["num_comments"], counted.get(post["id"], 0))
            if post["num_comments"] < BULK_MIN_COMMENTS:
                left_out["too little engagement"] += 1


def _read_and_save(chosen: dict[str, dict], files: dict, threads_dir: Path, never: set[str], now: datetime,
                   workers: int, result: ImportResult) -> None:
    by_subreddit: dict[str, list[str]] = {}
    for post in chosen.values():
        by_subreddit.setdefault(post["source"], []).append(post["id"])
    readable = {sub: ids for sub, ids in by_subreddit.items() if "comments" in files.get(sub, {})}
    result.missing_comments = sorted(set(by_subreddit) - set(readable))
    comments: dict[str, list[dict]] = {}
    for found in _run_all(collect_comments, [(str(files[sub]["comments"]), ids) for sub, ids in readable.items()],
                          workers):
        comments.update(found)
    for post_id, post in chosen.items():
        if post["source"] not in readable:
            continue
        thread = build_thread(post, comments.get(post_id, []), now, post.get("category"))
        if save_new(thread, threads_dir, never):
            result.saved.append(post_id)
            result.comments_saved += len(thread.comments)
        else:
            result.already_there.append(post_id)


def _log(result: ImportResult, chosen: dict[str, dict], library_dir: Path, now: datetime) -> None:
    """One line per type or request with threads saved, in the library's request log (as `library add` logs); one line
    per thread saved, with its provenance, in imports.jsonl."""
    saved = set(result.saved)
    requests = []
    for plan in [*result.requests, *result.types]:
        ids = [p["id"] for p in plan.chosen if p["id"] in saved]
        if not ids:
            continue
        line = {"at": now.isoformat(), "request": getattr(plan, "request", None) or plan.name, "status": "ok",
                "product_type": getattr(plan, "product_type", None) or plan.name, "thread_ids": ids,
                "via": "import-dump", "dump": BULK_DUMP}
        if isinstance(plan, TypePlan):
            kinds = Counter(p["kind"] for p in plan.chosen if p["id"] in saved)
            line["kinds"] = {kind: kinds[kind] for kind in THREAD_KINDS}
        requests.append(line)
    chosen_for: dict[str, list[tuple[str, str]]] = {}
    for plan in [*result.requests, *result.types]:
        for post in plan.chosen:
            chosen_for.setdefault(post["id"], []).append((getattr(plan, "request", None) or plan.name, post["kind"]))
    imports = []
    for thread_id in result.saved:
        post = chosen[thread_id]
        reasons = chosen_for.get(thread_id, [])
        imports.append({
            "at": now.isoformat(), "thread_id": thread_id, "community": post["subreddit"],
            "files": [post["file"], f"{post['source']}_comments.zst"], "dump": BULK_DUMP, "read_from": "arctic_shift",
            "chosen_for": list(dict.fromkeys(name for name, _ in reasons)), "kind": reasons[0][1] if reasons else None,
        })
    for name, lines in (("requests.jsonl", requests), ("imports.jsonl", imports)):
        if lines:
            with (library_dir / name).open("a", encoding="utf-8") as log:
                log.writelines(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)


# --- What a run says ---

def _kinds(counts: dict[str, int]) -> str:
    return " ".join(f"{counts.get(kind, 0):>3}" for kind in THREAD_KINDS)


def report(result: ImportResult) -> str:
    """What the run read, found, chose and saved: numbers, types and ids only, never anyone's words."""
    lines = [f"Read {len(result.files_read)} decided subreddits' post files: {result.posts_read:,} candidate posts "
             f"before engagement was counted and the library's own threads left out."]
    if result.skipped_files:
        lines.append(f"Left unread (not decided subreddits): {', '.join(result.skipped_files)}")
    for reason, n in sorted(result.left_out.items(), key=lambda item: -item[1]):
        lines.append(f"  left out, {reason}: {n:,}")
    lines.append("Per product type, by kind (advice, long-term use, warning): threads about it in the library, "
                 "candidates in the files, new threads chosen")
    lines.append(f"  {'type':<22} {'have':>11}   {'found':>11}   {'chosen':>11}")
    for plan in sorted(result.types, key=lambda p: (config.THREAD_CATEGORIES.index(p.category), p.name)):
        chosen = Counter(p["kind"] for p in plan.chosen)
        lines.append(f"  {plan.name:<22} {_kinds(plan.have)}   {_kinds(plan.found)}   {_kinds(chosen)}")
    if result.requests:
        lines.append("Requests (need-led): candidates talking about their needs, threads chosen")
        for plan in result.requests:
            lines.append(f"  {plan.request!r} ({plan.product_type or plan.status}): found {plan.found}, chosen "
                         f"{len(plan.chosen)}")
    total = len({p["id"] for plan in [*result.types, *result.requests] for p in plan.chosen})
    lines.append(f"New threads chosen: {total}")
    for problem in result.problems:
        lines.append(f"Note: {problem}")
    if result.dry_run:
        lines.append("This was a dry run: nothing saved.")
    else:
        lines.append(f"Saved {len(result.saved)} new thread files ({result.comments_saved:,} comments) in the library, "
                     "read from the archive's files (read_from \"arctic_shift\"): each waits for extraction "
                     "(python -m engine.extract todo) and its quotes for live checks, as any archive thread.")
        if result.already_there:
            lines.append(f"Already in the library, left as they were: {', '.join(result.already_there)}")
        if result.missing_comments:
            lines.append(f"Not read (no comments file): {', '.join(result.missing_comments)}")
    return "\n".join(lines)


# --- The raw files ---

def raw_files(folder: Path) -> list[Path]:
    """The raw files under the folder: every history file, and the download's part files."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    found = {path for pattern in RAW_PATTERNS for path in folder.rglob(pattern) if path.is_file()}
    return sorted(found)


def delete_raw(folder: Path) -> list[Path]:
    """Deletes the raw files under the folder (raw_files) and the folders they leave empty; returns what was deleted."""
    deleted = []
    for path in raw_files(folder):
        path.unlink()
        deleted.append(path)
    for directory in sorted({p.parent for p in deleted}, key=lambda p: len(p.parts), reverse=True):
        while directory != Path(folder) and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            directory = directory.parent
    return deleted


def _deadline(paths: list[Path]) -> datetime | None:
    """BULK_RAW_FILES_KEPT_HOURS after the first raw file was written (its creation time on this machine)."""
    times = [getattr(p.stat(), "st_birthtime", p.stat().st_mtime) for p in paths]
    return datetime.fromtimestamp(min(times), UTC) + timedelta(hours=BULK_RAW_FILES_KEPT_HOURS) if times else None


# --- Command line ---

def _import_options(words: list[str]) -> dict | None:
    """The folder and options typed after `import-dump`, or None when they don't make sense."""
    options = {"folder": None, "dry_run": False, "extra_types": [], "requests": [], "workers": WORKERS}
    words = list(words)
    while words:
        word = words.pop(0)
        name, equals, value = word.partition("=")
        if name == "--dry-run" and not equals:
            options["dry_run"] = True
            continue
        if name in ("--type", "--request", "--requests", "--workers"):
            if not equals:
                if not words:
                    return None
                value = words.pop(0)
            if name == "--type":
                type_name, colon, category = value.rpartition(":")
                if not colon or not type_name.strip() or category not in config.THREAD_CATEGORIES:
                    return None
                options["extra_types"].append((type_name.strip(), category))
            elif name == "--request" and value.strip():
                options["requests"].append(value.strip())
            elif name == "--requests" and Path(value).is_file():
                options["requests"] += [line.strip() for line in Path(value).read_text(encoding="utf-8").splitlines()
                                        if line.strip() and not line.startswith("#")]
            elif name == "--workers" and value.isdigit() and int(value) >= 1:
                options["workers"] = int(value)
            else:
                return None
            continue
        if word.startswith("--") or options["folder"] is not None:
            return None
        options["folder"] = Path(word)
    return options if options["folder"] is not None else None


def main(argv: list[str], library_dir: Path = DEFAULT_LIBRARY_DIR) -> int:
    command = argv[0] if argv else None
    if command == "import":
        options = _import_options(argv[1:])
        if options is None or not options["folder"].is_dir():
            print(__doc__)
            return 2
        result = import_dump(options["folder"], library_dir, requests=options["requests"],
                             extra_types=options["extra_types"], dry_run=options["dry_run"],
                             workers=options["workers"])
        print(report(result))
        return 0
    if command in ("raw-files", "delete-raw") and len(argv) == 2:
        folder = Path(argv[1])
        left = raw_files(folder)
        if command == "delete-raw":
            gigabytes = sum(p.stat().st_size for p in left) / 1e9
            deleted = delete_raw(folder)
            print(f"Deleted {len(deleted)} raw files ({gigabytes:.2f} GB) under {folder}.")
            left = raw_files(folder)
        if not left:
            print(f"Raw files under {folder}: none left.")
            return 0
        deadline = _deadline(left)
        gigabytes = sum(p.stat().st_size for p in left) / 1e9
        print(f"{len(left)} raw files left under {folder} ({gigabytes:.2f} GB); they must be deleted by "
              f"{deadline.astimezone(UK):%d %b %Y %H:%M %Z} ({BULK_RAW_FILES_KEPT_HOURS} hours after the first was "
              f"written): python -m engine.bulk_import delete-raw {folder}")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
