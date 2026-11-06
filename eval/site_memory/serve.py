"""The site run the way Cloud Run runs it (engine.web --public), from a container-like tree, with Reddit and Google
Cloud replaced by fake_cloud's stand-ins (nothing leaves this computer). Time can be compressed for reading ahead, SIGUSR1
writes the structure sizes (heapdump.py), and `--files` keeps saved checks as files, as the site did before 5 Nov 2026,
instead of in memory.
usage: python serve.py <tree> <port> <cache_dir> <bucket_dir> <pages_dir> --library DIR [--no-model] [--files]
       [--reload-seconds N] [--plan-seconds N] [--share-seconds N]"""
import inspect
import os
import signal
import sys
from pathlib import Path

tree, port = Path(sys.argv[1]).resolve(), int(sys.argv[2])
cache_dir, bucket_dir, pages_dir = Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
args = sys.argv[6:]
os.chdir(tree)
sys.path.insert(0, str(tree))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["CREDIBLE_RECS_ALLOWED_HOSTS"] = "127.0.0.1,localhost"
os.environ["PYTHONUNBUFFERED"] = "1"
if "--no-model" in args:
    os.environ["CREDIBLE_RECS_QUERY_MODEL"] = "off"


def opt(name, default=None):
    return float(args[args.index(name) + 1]) if name in args else default


import fake_cloud  # noqa: E402
from engine import feedback, live_check, on_demand as od, web  # noqa: E402
from engine.pipeline import cached_profiles  # noqa: E402
from engine.read_ahead import ReadAhead  # noqa: E402

if opt("--reload-seconds") is not None:
    od.BUNDLE_RELOAD_SECONDS = opt("--reload-seconds")
site, problems = web.site_from_env(os.environ, True)
assert site is not None, problems
web.store = feedback.store_from_env()
web.profiles = cached_profiles()
print("profile store:", type(web.profiles.store).__name__ if hasattr(web.profiles.store, "__class__") else "?", flush=True)
live_bucket = fake_cloud.FakeBucket(bucket_dir, "fake-live-checks", live_check.BUCKET_PREFIX)
in_memory = "in_memory" in inspect.signature(live_check.LiveChecker.__init__).parameters and "--files" not in args
web.live = fake_cloud.fake_live(cache_dir, live_bucket, pages_dir, in_memory=in_memory)
print(f"saved checks kept {'in memory' if in_memory else 'as files'}", flush=True)
settings = {}
if opt("--plan-seconds") is not None:
    settings["reload_seconds"] = opt("--plan-seconds")
if opt("--share-seconds") is not None:
    settings["share_seconds"] = opt("--share-seconds")
web.read_ahead = ReadAhead(web.live, **settings)
od_bucket = fake_cloud.FakeBucket(bucket_dir, "fake-on-demand", od.PREFIX)
library = Path(args[args.index("--library") + 1])
web.on_demand = od.SiteReader(od_bucket, library, job=None)


def dump(signum, frame):
    import heapdump
    print(heapdump.report(), flush=True)


def where_it_stands(signum, frame):  # SIGUSR2: a line about what is kept, for finding out why a run did what it did
    print(f"STATE remembered answers {len(web._answers)}, bundle generation {web.on_demand._bundle_generation}, "
          f"threads written from the bundle {len(web.on_demand._written)}, left to warm {len(web._left_to_warm)}", flush=True)


signal.signal(signal.SIGUSR1, dump)
signal.signal(signal.SIGUSR2, where_it_stands)
print(f"fake-cloud site on port {port} from {tree}, library {library}, read-ahead {settings}", flush=True)
web.serve(port, library, site)
