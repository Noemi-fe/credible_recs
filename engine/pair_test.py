"""The pairwise test's cards and decks (Noemi's decision of 20 Oct 2026): a short, blind test friends do in about 4
minutes, GET /test (engine/web.py, engine/templates/test.html).

Each visitor compares 6 pairs of answers to shopping questions: ours against ChatGPT's or Vetted's, two short cards
(at most 3 picks, each a name and a one-line why), and says "A", "B" or "About the same", with an optional line why.
The answers are kept through engine/feedback.py's store as their own kind, "blind_pair", and counted by
`python -m engine.blind_test tally-pairs`.

The cards are one file, data/library/blind_test_cards.json (git-ignored like the library, and baked into the site's
image by deploy/cloudrun/make_context.py), written from the 12 questions' captured answers (the 7 blind-test questions
and 5 drawn at random):

    {"version": 1, "captured": "2026-10-20", "questions": [
      {"id": "b01", "category": "skincare" | "kitchen" | "other",
       "text": {"en": "<the question as asked>", "it": "<Italian>"},
       "answers": {
         "ours":    {"picks": [{"name": "<product name>", "why": {"en": "<one line, at most 20 words>", "it": "..."}}],
                     "note": null},
         "chatgpt": {"picks": [...], "note": null},
         "vetted":  {"picks": [...], "note": {"en": "No recommendation given.", "it": "Nessun consiglio dato."}}}}]}

At most 3 picks an answer, in the tool's own order. "note" is set, with exactly that wording, only when the tool gave no
product picks (then "picks" is empty). No tool names, links, prices, currency, shops or availability anywhere in a
card: a visitor must not be able to tell the tools apart by them (problems() checks, and the page isn't served while a
card breaks a rule). Everything the file holds is the writer's own paraphrase of what each tool said, in short lines.

Each visitor's deck (build_deck): 6 different questions spread over the categories as evenly as the set allows (two
each from skincare, kitchen and other with the 12 questions; a category with fewer questions gives all of them and the
rest go to the others), in a random order; each question is ours against one rival, three against ChatGPT and three
against Vetted (so every visitor sees both), and ours is on side A in three of the six and on side B in the other three
(a random choice of which, so no side is ours more often). The deck is made when the page is asked for.

Nothing a visitor's browser holds may say which answer is ours or who the rival is (25 Oct 2026: found by trying the page,
which had carried both in its data, so in the page's source and in the tab's session storage). So the page is given only
each comparison's question and two cards, in the order to show them (public_deck), and the visit's id, which the server
made (new_visit). The deck follows from that id and a key only the server has (deck_for: the id, mixed with the key, seeds
the shuffles), so when an answer comes back with the id and the question, the server builds the same deck again and reads
the rival and the side off it (sides_of), and keeps them in the record. Nothing is kept between the page and the answers,
so every instance of the live site works the same: the key comes from a secret the site already holds (deck_key). The
id's last four letters are a fingerprint of the cards' questions (fingerprint): if the cards change while someone is part
way through, their answers are refused rather than given the wrong side.

    python -m engine.pair_test check [cards file]     reads the cards and lists every rule they break
    python -m engine.pair_test serve [--port N] [--cards DIR] [--store FILE]
        tries the page on this computer, http://127.0.0.1:8767/test: only the test's two routes, no library or model
        loaded; the cards are DIR's blind_test_cards.json (data/library by default), and the answers go to FILE (by
        default data/feedback/pairs-trial.jsonl, apart from the real feedback), which `python -m engine.blind_test
        tally-pairs FILE` counts. The deployed site keeps them through feedback.store_from_env as for any feedback.
"""

import copy
import hashlib
import hmac
import json
import os
import random
import re
import sys
from pathlib import Path

from engine.config import (BLIND_TEST_GIVEAWAYS, PAIR_TEST_MAX_PICKS, PAIR_TEST_MAX_WHY_WORDS,
                           PAIR_TEST_QUESTIONS_PER_VISITOR)
from engine.feedback import PAIR_LANGUAGES as LANGUAGES
from engine.feedback import PAIR_RIVALS as RIVALS

CARDS_NAME = "blind_test_cards.json"
LIBRARY_DIR = Path(__file__).resolve().parents[1] / "data" / "library"
TOOLS = ("ours", *RIVALS)
CATEGORIES = ("skincare", "kitchen", "other")
VERSION = 1
QUESTIONS_PER_VISITOR = PAIR_TEST_QUESTIONS_PER_VISITOR
MAX_PICKS = PAIR_TEST_MAX_PICKS
MAX_WHY_WORDS = PAIR_TEST_MAX_WHY_WORDS
NO_RECOMMENDATION = {"en": "No recommendation given.", "it": "Nessun consiglio dato."}
QUESTION_ID = re.compile(r"[A-Za-z0-9_-]{1,16}")
MAX_NAME_CHARS = 120
MAX_QUESTION_CHARS = 200


class CardsError(Exception):
    """The cards file is missing, malformed or breaks a rule; the message says which and where."""


# --- What a card must not carry: it would tell the tools apart, or say where and for how much to buy ---

_TOOL_NAMES = "|".join(re.escape(name).replace(r"\ ", r"[\s-]?") for name in (*BLIND_TEST_GIVEAWAYS, "chat gpt"))
# Checked in every text of a card, a pick's name included.
LEAKS = (
    (re.compile(rf"(?<![a-z])(?:{_TOOL_NAMES})(?![a-z])", re.IGNORECASE), "names a tool"),
    (re.compile(r"https?:|www\.|\b[\w-]+\.(?:com|co\.uk|org|net|io)\b", re.IGNORECASE), "has a link"),
    (re.compile(r"[£$€¥]|\b(?:gbp|usd|eur|pounds?|dollars?|euros?|pence|cents?|quid|bucks|sterline?|dollari|prezz[oi])\b"
                r"|\bprice[sd]?\b|\bdiscount(?:ed)?\b|\bon sale\b|\bbargain\b", re.IGNORECASE), "has a price"),
    (re.compile(r"\b(?:in|out of) stock\b|\bsold out\b|\bnot sold\b|\bsold (?:in|at|by|on|only|exclusively)\b"
                r"|\bdiscontinued\b|\bsecond-hand\b|\bfree (?:delivery|shipping)\b|\b(?:un)?availab(?:le|ility)\b"
                r"|\bdisponibil[ei]\b|\besaurit[oa]\b|\bfuori produzione\b|\bnon (?:è )?vendut[oa]\b",
                re.IGNORECASE), "says where it is sold or whether it is available"),
)
# Checked in a pick's why and a note, not in a product's name ("Amazon Kindle" is a product).
SHOPS = ("amazon", "argos", "currys", "john lewis", "sephora", "ulta", "walmart", "superdrug", "lookfantastic",
         "look fantastic", "cult beauty", "space nk", "waitrose", "tesco", "ebay", "etsy", "sainsbury's",
         "selfridges", "harrods", "debenhams", "lakeland", "dunelm", "boots uk", "marks & spencer")
_SHOP_NAMES = "|".join(re.escape(name) for name in SHOPS)
SHOP_LEAK = (re.compile(rf"(?<![a-z])(?:{_SHOP_NAMES})(?![a-z])", re.IGNORECASE), "names a shop")


def _leaks(text: str, is_name: bool = False) -> list[str]:
    found = [words for pattern, words in LEAKS if pattern.search(text)]
    if not is_name and SHOP_LEAK[0].search(text):
        found.append(SHOP_LEAK[1])
    return found


# --- Reading and checking the cards ---

def problems(cards: object) -> list[str]:
    """Every rule the cards break, each in words naming the question, tool and pick. [] when they are fine."""
    if not isinstance(cards, dict):
        return ["the file isn't one JSON object"]
    if cards.get("version") != VERSION:
        return [f'"version" must be {VERSION}']
    questions = cards.get("questions")
    if not isinstance(questions, list) or not questions:
        return ['"questions" must be a list with at least one question']
    found, seen = [], set()
    for number, question in enumerate(questions, start=1):
        found += _question_problems(question, number, seen)
    return found


def _question_problems(question: object, number: int, seen: set) -> list[str]:
    if not isinstance(question, dict):
        return [f"question {number}: not an object"]
    ident = question.get("id")
    where = ident if isinstance(ident, str) and ident else f"question {number}"
    if not isinstance(ident, str) or not QUESTION_ID.fullmatch(ident):
        return [f'{where}: "id" must be 1 to 16 letters, digits, "-" or "_"']
    found = []
    if ident in seen:
        found.append(f"{where}: the id is used twice")
    seen.add(ident)
    if question.get("category") not in CATEGORIES:
        found.append(f'{where}: "category" must be one of {", ".join(CATEGORIES)}')
    # The question is shown as it was asked ("under £30"): the rules about prices are for the answers.
    found += _text_problems(question.get("text"), f"{where} text", MAX_QUESTION_CHARS, leaks=False)
    answers = question.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(TOOLS):
        return found + [f'{where}: "answers" must hold exactly {", ".join(TOOLS)}']
    for tool in TOOLS:
        found += _answer_problems(answers[tool], f"{where} {tool}")
    return found


def _text_problems(text: object, where: str, limit: int, words: int | None = None, leaks: bool = True) -> list[str]:
    """A text in both languages: each a non-empty line, at most `limit` characters and `words` words, no leaks."""
    if not isinstance(text, dict) or set(text) != set(LANGUAGES):
        return [f'{where}: must be text in {" and ".join(LANGUAGES)}']
    found = []
    for language in LANGUAGES:
        value = text[language]
        if not isinstance(value, str) or not value.strip():
            found.append(f"{where} ({language}): empty")
            continue
        if len(value) > limit:
            found.append(f"{where} ({language}): {len(value)} characters; the limit is {limit}")
        if words is not None and len(value.split()) > words:
            found.append(f"{where} ({language}): {len(value.split())} words; the limit is {words}")
        if leaks:
            found += [f"{where} ({language}): {leak}" for leak in _leaks(value)]
    return found


def _answer_problems(answer: object, where: str) -> list[str]:
    if not isinstance(answer, dict) or set(answer) != {"picks", "note"}:
        return [f'{where}: must be {{"picks": [...], "note": ...}}']
    picks, note = answer["picks"], answer["note"]
    if not isinstance(picks, list):
        return [f'{where}: "picks" must be a list']
    found = []
    if len(picks) > MAX_PICKS:
        found.append(f"{where}: {len(picks)} picks; the limit is {MAX_PICKS}")
    for number, item in enumerate(picks, start=1):
        label = f"{where} pick {number}"
        if not isinstance(item, dict) or set(item) != {"name", "why"}:
            found.append(f'{label}: must be {{"name": ..., "why": ...}}')
            continue
        name = item["name"]
        if not isinstance(name, str) or not name.strip():
            found.append(f"{label}: the name is empty")
        else:
            if len(name) > MAX_NAME_CHARS:
                found.append(f"{label}: the name is {len(name)} characters; the limit is {MAX_NAME_CHARS}")
            found += [f"{label} name: {leak}" for leak in _leaks(name, is_name=True)]
        found += _text_problems(item["why"], f"{label} why", 400, words=MAX_WHY_WORDS)
    if picks and note is not None:
        found.append(f"{where}: has picks, so its note must be null")
    elif not picks and note != NO_RECOMMENDATION:
        found.append(f'{where}: gave no picks, so its note must be exactly {json.dumps(NO_RECOMMENDATION, ensure_ascii=False)}')
    return found


def load_cards(path: Path) -> dict:
    """The cards file, checked. Raises CardsError, naming everything wrong with it."""
    path = Path(path)
    try:
        cards = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CardsError(f"{path} doesn't exist: the test has no cards yet") from None
    except (OSError, ValueError) as error:
        raise CardsError(f"{path} can't be read as JSON ({type(error).__name__})") from None
    found = problems(cards)
    if found:
        raise CardsError(f"{path.name}: " + "; ".join(found))
    return cards


def cards_file(library_dir: Path | None = None) -> Path:
    return Path(library_dir or LIBRARY_DIR) / CARDS_NAME


_loaded: dict[str, tuple[tuple[int, int] | None, dict | None, str]] = {}  # path -> (file stamp, cards, why not)


def _load_remembered(library_dir: Path) -> tuple[dict | None, str]:
    path = cards_file(library_dir)
    try:
        info = path.stat()
        stamp = (info.st_mtime_ns, info.st_size)
    except OSError:
        stamp = None
    remembered = _loaded.get(str(path))
    if remembered is None or remembered[0] != stamp:
        try:
            cards, why = load_cards(path), ""
        except CardsError as error:
            cards, why = None, str(error)
        remembered = _loaded[str(path)] = (stamp, cards, why)
    return remembered[1], remembered[2]


def cards_in(library_dir: Path | None = None) -> dict | None:
    """The cards in a library folder, checked and remembered until the file changes; None when the file is missing or
    breaks a rule (why_closed says which)."""
    return _load_remembered(library_dir)[0]


def why_closed(library_dir: Path | None = None) -> str:
    """Why cards_in gives none (words for whoever runs the server, never for a visitor); "" when the cards are fine."""
    return _load_remembered(library_dir)[1]


# --- A visitor's deck ---

def build_deck(cards: dict, rng: random.Random, size: int = QUESTIONS_PER_VISITOR) -> list[dict]:
    """`size` comparisons for one visitor (fewer when the cards have fewer questions), as described at the top. Each is
    {"question": id, "text": {"en", "it"}, "rival": "chatgpt" | "vetted", "ours_side": "A" | "B",
     "cards": {"A": card, "B": card}}: copies, so the cards themselves never change."""
    questions = cards.get("questions") or []
    if not questions:
        raise CardsError("the cards hold no questions")
    size = min(size, len(questions))
    by_category: dict[str, list[dict]] = {}
    for question in questions:
        by_category.setdefault(question["category"], []).append(question)
    for group in by_category.values():
        rng.shuffle(group)
    chosen = []
    while len(chosen) < size:  # a round takes one question from each category that has any left, in a random order
        round_ = [category for category, group in by_category.items() if group]
        rng.shuffle(round_)
        for category in round_[:size - len(chosen)]:
            chosen.append(by_category[category].pop())
    rng.shuffle(chosen)
    rivals = [RIVALS[number % len(RIVALS)] for number in range(size)]
    sides = [("A", "B")[number % 2] for number in range(size)]
    rng.shuffle(rivals)
    rng.shuffle(sides)
    deck = []
    for question, rival, side in zip(chosen, rivals, sides):
        other = "B" if side == "A" else "A"
        shown = {side: copy.deepcopy(question["answers"]["ours"]), other: copy.deepcopy(question["answers"][rival])}
        deck.append({"question": question["id"], "text": copy.deepcopy(question["text"]), "rival": rival,
                     "ours_side": side, "cards": {"A": shown["A"], "B": shown["B"]}})
    return deck


# --- A visit: its id, and the deck that follows from it ---

KEY_SETTINGS = ("CREDIBLE_RECS_TEST_KEY", "HF_TOKEN")  # in this order: the first one set makes the key
VISIT_FINGERPRINT_CHARS = 4


def deck_key(environ=None) -> bytes:
    """The key that, with a visit's id, decides its deck: worked out (HMAC-SHA-256, so the secret itself can't be read
    back from it) from CREDIBLE_RECS_TEST_KEY, else from HF_TOKEN, which the live site holds as a secret already, so every
    instance and every restart get the same key. With neither set (a trial on this computer, the tests) a fresh random
    key: the deck is the same for one running server and nobody else."""
    environ = os.environ if environ is None else environ
    for name in KEY_SETTINGS:
        secret = (environ.get(name) or "").strip()
        if secret:
            return hmac.new(secret.encode("utf-8"), b"credible-recs pairwise test: decks", hashlib.sha256).digest()
    return os.urandom(32)


def fingerprint(cards: dict) -> str:
    """Four letters that change when the cards' questions, their categories or their order do, and not when a card's
    words do: what decides a deck. The end of every visit's id."""
    shape = json.dumps([[question["id"], question["category"]] for question in cards.get("questions") or []])
    return hashlib.sha256(shape.encode("utf-8")).hexdigest()[:VISIT_FINGERPRINT_CHARS]


def new_visit(cards: dict, rng: random.Random) -> str:
    """A new visit's id: 24 random letters and digits from `rng` (the system's, on the site) and the cards' fingerprint."""
    return f"{rng.getrandbits(96):024x}{fingerprint(cards)}"


def deck_for(cards: dict, visit: str, key: bytes, size: int = QUESTIONS_PER_VISITOR) -> list[dict]:
    """The visit's deck, in full (build_deck's, with the rival and the side): the same whenever it is asked for, by whoever
    holds `key`."""
    seed = int.from_bytes(hmac.new(key, visit.encode("utf-8"), hashlib.sha256).digest(), "big")
    return build_deck(cards, random.Random(seed), size)


def sides_of(cards: dict, visit: str, question: str, key: bytes) -> tuple[str, str] | None:
    """(the rival, the side ours was on) for a question of the visit's deck; None when the visit's id is for other cards
    (their fingerprint differs) or its deck never held that question."""
    if visit[-VISIT_FINGERPRINT_CHARS:] != fingerprint(cards):
        return None
    for item in deck_for(cards, visit, key):
        if item["question"] == question:
            return item["rival"], item["ours_side"]
    return None


def public_deck(deck: list[dict]) -> list[dict]:
    """What the page is given of a deck: each comparison's question, its text and its two cards in the order to show
    them. Never the rival or ours' side: they stay with the server."""
    return [{"question": item["question"], "text": copy.deepcopy(item["text"]), "cards": copy.deepcopy(item["cards"])}
            for item in deck]


# --- Trying it on this computer ---

TRIAL_PORT = 8767
TRIAL_STORE = Path(__file__).resolve().parents[1] / "data" / "feedback" / "pairs-trial.jsonl"


def trial_options(argv: list[str]) -> tuple[int, Path, Path] | None:
    """--port N, --cards DIR and --store FILE, in any order, each once; None if anything else is given."""
    values = {"--port": None, "--cards": None, "--store": None}
    if len(argv) % 2:
        return None
    for name, value in zip(argv[::2], argv[1::2]):
        if name not in values or values[name] is not None or (name == "--port" and not value.isdigit()):
            return None
        values[name] = value
    return (int(values["--port"]) if values["--port"] else TRIAL_PORT,
            Path(values["--cards"]) if values["--cards"] else LIBRARY_DIR,
            Path(values["--store"]) if values["--store"] else TRIAL_STORE)


def trial_server(library_dir: Path, store_path: Path, port: int = TRIAL_PORT):
    """A local server (engine.web, local mode) that serves the test and takes its answers into `store_path` and
    nothing else: no library is loaded, no model, no answers are worked out. Start it with serve_forever()."""
    from engine import feedback, web

    web.store = feedback.LocalStore(store_path)
    return web.make_server(port, Path(library_dir))


# --- The command line ---

def main(argv: list[str]) -> int:
    if argv[:1] == ["check"] and len(argv) in (1, 2):
        path = Path(argv[1]) if len(argv) == 2 else cards_file()
        try:
            cards = load_cards(path)
        except CardsError as error:
            print(f"Not ready: {error}")
            return 1
        counts = {category: sum(q["category"] == category for q in cards["questions"]) for category in CATEGORIES}
        print(f"{len(cards['questions'])} questions ({', '.join(f'{c} {n}' for c, n in counts.items())}): the cards "
              "follow every rule. Each visitor gets "
              f"{min(QUESTIONS_PER_VISITOR, len(cards['questions']))} of them.")
        return 0
    if argv[:1] == ["serve"]:
        options = trial_options(argv[1:])
        if options is not None:
            port, library_dir, store_path = options
            if not cards_file(library_dir).is_file():
                print(f"No cards yet: {cards_file(library_dir)} doesn't exist.")
                return 1
            server = trial_server(library_dir, store_path, port)
            print(f"Open http://127.0.0.1:{server.server_address[1]}/test in your browser. Answers are kept in "
                  f"{store_path}. Ctrl+C stops it.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
