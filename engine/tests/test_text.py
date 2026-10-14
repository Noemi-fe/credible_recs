"""engine/text.py's one_edit_apart: one letter added, removed or changed, and nothing else (module 4's spelling slips,
module 2's product names, module 5's name words)."""

import itertools
import random

from engine.text import one_edit_apart


def one_edit_apart_by_trying(a: str, b: str) -> bool:
    """The rule as first written (until 13 Oct 2026): every letter compared, every letter tried out. The reference the
    quicker one must always equal."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def test_one_letter_added_removed_or_changed():
    assert one_edit_apart("zojirushi", "zojurushi")
    assert one_edit_apart("kettle", "kettles")
    assert one_edit_apart("kettles", "kettle")
    assert one_edit_apart("hur", "hurr")
    assert one_edit_apart("a", "")
    assert one_edit_apart("cat", "bat")


def test_anything_else_is_not_one_edit_apart():
    assert not one_edit_apart("kettle", "kettle")
    assert not one_edit_apart("kettle", "kettel")  # two letters changed (moved)
    assert not one_edit_apart("cat", "cart s")
    assert not one_edit_apart("", "")
    assert not one_edit_apart("ab", "ba")


def test_every_pair_of_short_words_agrees_with_trying_every_letter():
    words = ["".join(p) for n in range(5) for p in itertools.product("abc", repeat=n)]
    for a in words:
        for b in words:
            assert one_edit_apart(a, b) == one_edit_apart_by_trying(a, b), (a, b)


def test_made_up_words_agree_with_trying_every_letter():
    rng = random.Random(13)
    for _ in range(20000):
        a = "".join(rng.choice("aabcde") for _ in range(rng.randint(0, 10)))
        b = list(a)
        for _ in range(rng.randint(0, 2)):
            kind = rng.choice(["add", "drop", "change"])
            at = rng.randint(0, len(b))
            if kind == "add":
                b.insert(at, rng.choice("abcdef"))
            elif b and at < len(b):
                if kind == "drop":
                    del b[at]
                else:
                    b[at] = rng.choice("abcdef")
        b = "".join(b)
        assert one_edit_apart(a, b) == one_edit_apart_by_trying(a, b), (a, b)
