"""A bundle of N threads 'read on demand' for the fake on-demand bucket, made from the biggest library threads under new
ids (a thread and its extraction, as the library saves them), so the site has N threads more than the image holds.
usage: python make_bundle.py <tree> <library> <bucket_dir> [N]"""
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

tree, library, bucket_dir = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
count = int(sys.argv[4]) if len(sys.argv) > 4 else 300
mode = sys.argv[5] if len(sys.argv) > 5 else "random"  # random: a typical sample of library threads; biggest: the largest
os.chdir(tree)
sys.path.insert(0, str(tree))
from engine.gold import load_threads  # noqa: E402
from engine.on_demand import Bundle, Item, THREADS_NAME, PREFIX  # noqa: E402

files = sorted((library / "threads").glob("*.json"), key=lambda p: -p.stat().st_size)
files = [p for p in files if (library / "extracted" / p.name).exists()]
if mode == "random":
    import random
    files = random.Random(7).sample(files, count)
else:
    files = files[:count]
bundle = Bundle()
now = datetime.now(UTC).isoformat()
for n, path in enumerate(files):
    thread_text, extraction_text = path.read_text(encoding="utf-8"), (library / "extracted" / path.name).read_text(encoding="utf-8")
    raw = json.loads(thread_text)
    old, new = raw["id"], f"zz{n:04d}"
    for comment in raw["comments"]:
        cid = comment["id"]
        for q in ('"%s"',):
            thread_text = thread_text.replace(q % cid, q % (cid + f"q{n}"))
            extraction_text = extraction_text.replace(q % cid, q % (cid + f"q{n}"))
        thread_text = thread_text.replace(f"/{cid}/", f"/{cid}q{n}/")
    thread_text = thread_text.replace(f"/comments/{old}/", f"/comments/{new}/").replace(f'"id": "{old}"', f'"id": "{new}"', 1)
    extraction_text = extraction_text.replace(f'"thread_id": "{old}"', f'"thread_id": "{new}"')
    bundle.threads[new] = Item(thread=thread_text, extraction=extraction_text, entry="loadtest", product_type="loadtest",
                               added_at=now, slimmed=True)
(bucket_dir / PREFIX).mkdir(parents=True, exist_ok=True)
data = json.dumps(bundle.as_json(), ensure_ascii=False).encode("utf-8")
(bucket_dir / PREFIX / THREADS_NAME).write_bytes(data)
print(f"bundle of {len(bundle.threads)} threads, {len(data)/2**20:.1f} MB")
# check they load: new ids, unique comment ids, valid
import tempfile, shutil
tmp = Path(tempfile.mkdtemp()); (tmp / "threads").mkdir(); (tmp / "extracted").mkdir()
for tid, item in bundle.threads.items():
    (tmp / "threads" / f"{tid}.json").write_text(item.thread, encoding="utf-8")
    (tmp / "extracted" / f"{tid}.json").write_text(item.extraction, encoding="utf-8")
problems = []
threads = load_threads(tmp / "threads", skip_broken=True, problems=problems)
from engine.extract import check_extractions
checked, p2 = check_extractions(tmp / "threads", threads)
print(f"loads: {len(threads)} threads, {sum(len(t.comments) for t in threads)} comments, {len(problems)} thread problems, "
      f"{len(p2)} extraction problems, {sum(len(r.kept) for r in checked.values())} mentions kept")
shutil.rmtree(tmp)
