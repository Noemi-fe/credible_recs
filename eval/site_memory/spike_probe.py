"""The memory the site's taking in of an on-demand bundle needs (engine.on_demand.SiteReader.load_threads), alone in a
process: the lifetime peak footprint above the footprint before it. usage: run from a tree: python spike_probe.py <bundle threads.json>"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402
import fake_cloud  # noqa: E402
from engine import on_demand as od  # noqa: E402

src = Path(sys.argv[1])
work = Path(tempfile.mkdtemp())
(work / "bucket" / od.PREFIX).mkdir(parents=True)
shutil.copyfile(src, work / "bucket" / od.PREFIX / od.THREADS_NAME)
(work / "lib" / "threads").mkdir(parents=True)
(work / "lib" / "extracted").mkdir(parents=True)
reader = od.SiteReader(fake_cloud.FakeBucket(work / "bucket", "b", od.PREFIX), work / "lib", job=None)
before = mem.mib(os.getpid())
n = reader.load_threads()
after = mem.mib(os.getpid())
print(f"bundle {src.stat().st_size / 2**20:.1f} MiB, {n} threads written: footprint before {before[0]:.0f} MiB, "
      f"peak {after[1]:.0f} MiB (+{after[1] - before[0]:.0f}), after {after[0]:.0f} MiB")
shutil.rmtree(work)
