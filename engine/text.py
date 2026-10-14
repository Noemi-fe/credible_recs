"""Small text helpers shared by several modules."""


def one_edit_apart(a: str, b: str) -> bool:
    """True if one letter added, removed or changed turns a into b.

    Read from the first letter where they differ (latency, 13 Oct 2026: it compared every letter, and for a letter
    added tried every place for it; modules 4 and 5 ask it hundreds of thousands of times): what comes after that letter
    must then be the same, in both words when one letter changed, or with the longer word's letter left out."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a  # a is never the longer
    i = 0
    for x, y in zip(a, b):
        if x != y:
            break
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]
