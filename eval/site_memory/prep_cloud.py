"""The fake cloud for a run of the site's memory under load, from the library as the image holds it:
- pages/: every readable comment's embed page, for the fake Reddit;
- bucket/live_check/bundle.json: the checks of the last 48 hours as the live bucket holds them (~18,400, like the live
  site's 18,946), so a server started 'right after a deploy' with an empty folder reads them in (load_bundle);
- bucket/live_check/plan.json: the daily plan (7,000 answers' comments due, 600 fallback, 4,500 to verify);
- plans/plan_N.json: later daily plans, each with 4,500 other comments to verify (days of reading ahead, compressed).
usage: run from a tree: python prep_cloud.py <outdir>"""
import json
import random
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from engine import library_cache  # noqa: E402
from engine.live_check import _entry_name, embed_url  # noqa: E402
from engine.read_ahead import plan_bytes  # noqa: E402

out = Path(sys.argv[1])
pages, bucket, plans = out / "pages", out / "bucket", out / "plans"
for d in (pages, bucket, plans):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
(bucket / "live_check").mkdir()
kept = library_cache.loaded(Path.cwd() / "data" / "library" / "threads")
now = datetime.now(UTC)
comments = {c.id: c for t in kept.threads for c in t.comments if c.status == "ok" and c.body}
cited = list(dict.fromkeys(m.comment_id for res in kept.checked.values() for m in res.kept if m.comment_id in comments))
cited_set = set(cited)
rest = [i for i in comments if i not in cited_set]
answers, fallback = cited[:7000], cited[7000:7600]
pool = cited[7600:] + rest
verify = pool[:4500]
rng = random.Random(3)
others = [i for i in cited if i not in set(answers)]
in_bundle = {i: timedelta(hours=41) for i in answers} | {i: timedelta(hours=10) for i in rng.sample(others, min(11400, len(others)))}
checks = {}
for i, c in comments.items():
    text = " ".join(c.body.split())
    name = _entry_name(embed_url(c.url))
    (pages / name).write_text(json.dumps({"fetched_at": now.isoformat(), "text": text}, ensure_ascii=False), encoding="utf-8")
    if i in in_bundle:
        checks[name] = {"fetched_at": (now - in_bundle[i]).isoformat(), "text": text}
(bucket / "live_check" / "bundle.json").write_text(json.dumps({"written_at": now.isoformat(), "checks": checks},
                                                              ensure_ascii=False), encoding="utf-8")
url = lambda ids: [comments[i].url for i in ids]
(bucket / "live_check" / "plan.json").write_bytes(plan_bytes(url(answers), url(verify), {}, now, [], url(fallback)))
n = 0
for start in range(4500, len(pool), 4500):
    n += 1
    (plans / f"plan_{n}.json").write_bytes(plan_bytes(url(answers), url(pool[start:start + 4500]), {}, now, [], url(fallback)))
print(f"{len(comments)} pages; bundle of {len(checks)} checks ({(bucket / 'live_check' / 'bundle.json').stat().st_size / 2**20:.1f} MiB); "
      f"plan: {len(answers)} answers, {len(fallback)} fallback, {len(verify)} verify; {n} later plans of up to 4,500 to verify "
      f"({len(pool)} in the pool)")
