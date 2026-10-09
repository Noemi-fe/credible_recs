"""The thin end-to-end slice: one request, typed in plain words, through modules 1 to 7 to a top 3.

    request ──1 query──> category, product type ──2 retrieval──> the library's most relevant threads
            ──3 extraction──> their checked mentions and notes (saved files; quotes already verified once)
            ──4 matching──> products and kinds ──5 credibility──> a weight per mention
            ──6 ranking──> scores, minimum-evidence rule, skip list ──7 answer──> picks with quotes re-verified

Every step is a module of its own; this file only passes each one's output to the next. Three filters sit here:
- only threads about the product are read: its title or post must name it (engine.sources.relevance of at least
  PIPELINE_MIN_RELEVANCE). A coffee thread that mentions kettles in passing isn't about kettles, and its grinders
  would otherwise be ranked for a kettle request;
- products of another type are left out: a skillet praised in a kettle thread is a real product, but not an answer
  to a kettle request. A product counts as another type when one of its names says so ("Lodge cast iron
  skillet") and none names the requested type. A name that says nothing ("Zojirushi") stays in. (Rules for now;
  the AI could tag each product's type when it reads a thread.)
- loose groups (a brand or line that fits several products, such as "Lodge" or "CeraVe") are left out of the
  ranking unless PIPELINE_INCLUDE_LOOSE says otherwise: their mentions can't count for any one product.
Both lists are kept on the result, so nothing is dropped silently.

Writers' standing (account age, karma, contributions, flair) isn't in the saved threads: Parse gives only names.
With `profiles` (engine.profiles.StoredProfiles in the command line, the web demo and the evaluation), it is filled in
from the library's profile store (kept for LIBRARY_REFRESH_DAYS, Noemi's decision of 9 Oct 2026) and Arctic Shift's
48-hour cache, never waiting on a call; `python -m engine.profiles warm data/library/threads` fills both beforehand.

Command line:
    python -m engine.pipeline "<request>"     prints the answer, from data/library
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.answer import Answer, comment_bodies, render_markdown, write_answer
from engine.config import PIPELINE_INCLUDE_LOOSE, PIPELINE_MAX_THREADS, PIPELINE_MIN_RELEVANCE
from engine.credibility import badges, mention_weight, score_evidence, score_voice
from engine.extract import CheckResult, load_checked
from engine.group_kinds import KindMention, group_kinds, kinds_of, placements
from engine.group_products import ProductGroup, ProductMention, group_of, group_products
from engine.library import DEFAULT_LIBRARY_DIR
from engine.models import Thread
from engine.profiles import ProfileStore, StoredProfiles, with_profiles
from engine.query import PRODUCT_TYPES, ParsedQuery, parse_query
from engine.rank import KindNote, RankingResult, ScoredMention, rank_products
from engine.sources import LocalSource, mentions_product, relevance


@dataclass
class PipelineResult:
    query: ParsedQuery
    threads_used: list[str] = field(default_factory=list)  # thread ids, most relevant first
    ranking: RankingResult | None = None
    answer: Answer | None = None  # None when module 1 asks a question or says no
    bodies: dict[str, str] = field(default_factory=dict)  # comment id -> text, to re-check quotes
    left_out_as_other_type: list[str] = field(default_factory=list)  # product names
    left_out_loose: list[str] = field(default_factory=list)  # brand or line names

    def text(self) -> str:
        """The answer as Markdown, or module 1's question or polite no."""
        if self.answer is None:
            return self.query.question or self.query.message or "Nothing to show."
        return render_markdown(self.answer)


def answer_request(request: str, library_dir: Path = DEFAULT_LIBRARY_DIR, max_threads: int = PIPELINE_MAX_THREADS,
                   profiles=None) -> PipelineResult:
    """Runs modules 1 to 7 on the saved library and returns everything each step decided.

    `profiles`: where writers' standing comes from (an object with user_stats and comment_flairs, such as
    engine.profiles.StoredProfiles); None leaves the writers as saved, known by name only.
    """
    query = parse_query(request)
    result = PipelineResult(query)
    if query.status != "ok":
        return result
    threads_dir = Path(library_dir) / "threads"
    threads = LocalSource(threads_dir).find_threads(query, limit=max_threads)
    threads = [t for t in threads if relevance(t, query.product_type) >= PIPELINE_MIN_RELEVANCE]
    checked = {tid: res for tid, res in load_checked(threads_dir).items() if tid in {t.id for t in threads}}
    threads = [t for t in threads if t.id in checked]  # a thread the AI hasn't read yet has nothing to offer
    if profiles is not None:
        threads = [with_profiles(t, profiles, {m.comment_id for m in checked[t.id].kept}).thread for t in threads]
    result.threads_used = [t.id for t in threads]
    result.bodies = comment_bodies(threads)

    groups = group_products(_product_mentions(checked))
    kept_groups = _groups_to_rank(groups, query, result)
    kinds = group_kinds(_kind_mentions(checked), kept_groups, query.category, query.product_type or "")
    scored, kind_notes = _score(threads, checked, kept_groups, kinds)
    result.ranking = rank_products(scored, query.category, kind_notes, placements(kinds))
    result.answer = write_answer(result.ranking, result.bodies, query.product_type)
    return result


# --- Module 4: products and kinds ---

def _product_mentions(checked: dict[str, CheckResult]) -> list[ProductMention]:
    return [ProductMention(tid, m.comment_id, m.product, m.category, m.stance) for tid, res in checked.items() for m in res.kept]


def _kind_mentions(checked: dict[str, CheckResult]) -> list[KindMention]:
    return [KindMention(tid, n.comment_id, n.about, n.stance) for tid, res in checked.items() for n in res.kept_notes]


def _groups_to_rank(groups: list[ProductGroup], query: ParsedQuery, result: PipelineResult) -> list[ProductGroup]:
    """The product groups worth ranking for this request; the others are named on the result."""
    kept = []
    for group in groups:
        if group.category != query.category:
            continue  # the ranking only looks at the request's category anyway
        if group.loose and not PIPELINE_INCLUDE_LOOSE:
            result.left_out_loose.append(group.name)
        elif _another_type(group, query):
            result.left_out_as_other_type.append(group.name)
        else:
            kept.append(group)
    return kept


def _another_type(group: ProductGroup, query: ParsedQuery) -> bool:
    """Whether the product's names say it is another type of product than the one requested, and none says it isn't."""
    names = list(group.names)
    if any(mentions_product(name, query.product_type) for name in names):
        return False
    others = [p.name for p in PRODUCT_TYPES if p.category == query.category and p.name != query.product_type]
    return any(mentions_product(name, other) for name in names for other in others)


# --- Module 5: a weight for every mention and note ---

def _score(threads: list[Thread], checked: dict[str, CheckResult], groups: list[ProductGroup], kinds) -> tuple[list[ScoredMention], list[KindNote]]:
    by_id = {t.id: t for t in threads}
    group_by_mention = group_of(groups)
    kind_groups = kinds_of(kinds)
    scored, notes = [], []
    for tid, res in checked.items():
        thread = by_id[tid]
        comments = {c.id: c for c in thread.comments}
        voices = {}
        for m in res.kept:
            group = group_by_mention.get(ProductMention(tid, m.comment_id, m.product, m.category, m.stance))
            if group is None:
                continue  # left out above: another category, another type, or a loose name
            comment = comments[m.comment_id]
            voice = voices.setdefault(m.comment_id, score_voice(comment, thread, res.kept_agreements))
            others = [o.product for o in res.kept if o.comment_id == m.comment_id and o.product != m.product]
            evidence = score_evidence(comment, m.product, m.stance, others)
            scored.append(ScoredMention(
                product_key=group.key, product_name=group.name, category=group.category, thread_id=tid,
                comment_id=m.comment_id, comment_url=str(comment.url), stance=m.stance,
                weight=mention_weight(voice, evidence, m.stance), voice=voice.level, evidence=evidence.level,
                quote=m.quote, badges=badges(voice, evidence),
            ))
        for n in res.kept_notes:
            comment = comments[n.comment_id]
            voice = voices.setdefault(n.comment_id, score_voice(comment, thread, res.kept_agreements))
            evidence = score_evidence(comment, n.about, n.stance)
            for kind in kind_groups.get(KindMention(tid, n.comment_id, n.about, n.stance), []):
                notes.append(KindNote(
                    kind_key=kind.key, kind_name=kind.name, thread_id=tid, comment_id=n.comment_id,
                    comment_url=str(comment.url), stance=n.stance, weight=mention_weight(voice, evidence, n.stance),
                    voice=voice.level, quote=n.quote, badges=badges(voice, evidence),
                ))
    return scored, notes


def cached_profiles() -> StoredProfiles:
    """Writers' standing from the library's profile store, then the Arctic Shift cache; never a call. What the command
    line, the demo and the evaluation use."""
    from engine.arctic_shift import ArcticShiftClient

    return StoredProfiles(ProfileStore(DEFAULT_LIBRARY_DIR / "profiles.json"), ArcticShiftClient())


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    result = answer_request(" ".join(argv), profiles=cached_profiles())
    print(result.text())
    if result.answer is not None:
        print(f"\n(threads used: {', '.join(result.threads_used)}; left out as another type: "
              f"{len(result.left_out_as_other_type)}; brand or line names left out: {len(result.left_out_loose)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
