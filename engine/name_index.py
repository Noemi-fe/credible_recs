"""An index of a list's product names, to find the entries that could be the same product as a name without comparing
the name with every entry (15 Oct 2026, the buyable-picks builder).

Why: researchers' findings grow the price list from about 160 entries to over 1,000, and the product pages list from
none to about 800 (engine/buyable.py). An answer looks up every product it ranks in both, and comparing each name with
every entry took about 25 microseconds a pair: seconds a cold answer.

How it stays exact: module 4's rule (engine.match_products.same_product) decides every pair, as before; the index only
leaves out entries the matcher's own quick look (match_products._cannot_match) rules out. That look says no unless
every word of the shorter of two names is one of the longer's words or could be a spelling slip of one (the same first
letter, a length within one), the shorter's first word slipping only at the longer's start; or unless neighbouring
words of one are written as one word of the other ("soon jung", "soonjung"), which it leaves to the matcher. An "and"
only one name writes is left out of both first. So the entries that could match a name are:
- with the name as the shorter: those having, for each of its words but "and", that word or one a slip of it could be
  (one list per word, intersected);
- with the entry as the shorter: those whose first word (or first word but "and") is one of the name's words, or a slip
  of the name's first word could be it;
- and those where a run of neighbouring words of one is a word of the other.
Matching entries are a subset of these, which the matcher then checks as before, in the list's order. A name of no
words but "and" gets every entry, as does an entry with such a name. Words are as module 4 reads them (product_words,
with the category's known short names written out), so short names ("SGP") and UK names ("Sage") find their entries.
"""

from collections import defaultdict

from engine.match_products import AND, Aliases, _runs, _slip_keys, product_words


class NameIndex:
    """The entries of one category of a list, by the words of each one's names (its own and the others it goes by)."""

    def __init__(self, names: list[list[str]], aliases: Aliases):
        """`names`: for each entry, in the list's order, its names ([product, *also_called])."""
        self._aliases = aliases
        self._count = len(names)
        self._by_word: dict[str, set[int]] = defaultdict(set)  # a word (or joined run) -> entries with it
        self._by_length: dict[tuple[str, int], set[int]] = defaultdict(set)  # (first letter, length) of any word
        self._by_first: dict[str, set[int]] = defaultdict(set)  # an entry name's first word (and first but "and")
        self._first_length: dict[tuple[str, int], set[int]] = defaultdict(set)  # the same, by first letter and length
        self._runs: dict[str, set[int]] = defaultdict(set)  # a run of neighbouring words joined -> entries with it
        self._always: set[int] = set()  # entries with a name of no words but "and": left to the matcher, every time
        for position, known in enumerate(names):
            for name in known:
                words = tuple(product_words(name, aliases))
                if set(words) <= {AND}:
                    self._always.add(position)
                    continue
                for word in words:
                    self._by_word[word].add(position)
                    self._by_length[(word[:1], len(word))].add(position)
                for first in {words[0], *[w for w in words if w != AND][:1]}:
                    self._by_first[first].add(position)
                    self._first_length[(first[:1], len(first))].add(position)
                for run in _runs(words):
                    self._runs[run].add(position)

    def candidates(self, name: str) -> list[int]:
        """The positions, in the list's order, of the entries that could be the same product as `name`."""
        words = tuple(product_words(name, self._aliases))
        own = [word for word in dict.fromkeys(words) if word != AND]
        if not own:
            return list(range(self._count))
        found = set(self._always)
        # The name as the shorter: every one of its words (but "and") found in the entry, or a slip of one.
        lists = sorted((self._covering(word) for word in own), key=len)
        found |= lists[0].intersection(*lists[1:])
        # The entry as the shorter: its first word is one of the name's, or a slip of the name's first word.
        for word in own:
            found |= self._by_first.get(word, set())
        for first in {words[0], own[0]}:
            for key in _slip_keys(first):
                found |= self._first_length.get(key, set())
        # Words written apart in one and as one in the other.
        for word in own:
            found |= self._runs.get(word, set())
        for run in _runs(words):
            found |= self._by_word.get(run, set())
        return sorted(found)

    def _covering(self, word: str) -> set[int]:
        """The entries with this word, or with a word it could be a slip of."""
        found = set(self._by_word.get(word, ()))
        for key in _slip_keys(word):
            found |= self._by_length.get(key, set())
        return found
