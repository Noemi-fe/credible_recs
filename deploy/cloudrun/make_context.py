"""Builds the private bundle Google Cloud Run builds the site from (Noemi, 12 Oct 2026): the code at the current
commit, the saved library the answers read, and the Dockerfile next to this file.

The bundle is uploaded to Cloud Build in Noemi's own project and becomes a private image there: the library (Reddit
text) is never public, and never in this repository. What goes in:
- the code as committed (`git archive HEAD`), so nothing uncommitted and nothing git ignores: no .env, no caches;
- data/library's threads/*.json, extracted/*.json and profiles.json, the files answers read (not the request log or
  the candidate lists);
- deploy/cloudrun/Dockerfile, as the bundle's Dockerfile.
check_bundle then refuses a bundle holding a secret file or a cache, whatever put it there.

    python -m deploy.cloudrun.make_context <empty or new folder>
"""

import shutil
import subprocess
import sys
import tarfile
import io
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_PATTERNS = ("threads/*.json", "extracted/*.json", "profiles.json")
FORBIDDEN = (".env", ".cache", "models", ".git")  # secrets, caches, the 1.1 GB model (downloaded at build) and history


class BundleError(Exception):
    pass


def copy_library(library: Path, dest: Path) -> int:
    """Copies the library files answers read into `dest`; returns how many."""
    count = 0
    for pattern in LIBRARY_PATTERNS:
        for path in sorted(Path(library).glob(pattern)):
            target = Path(dest) / path.relative_to(library)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
    return count


def check_bundle(bundle: Path) -> None:
    """Raises BundleError when the bundle holds a secret file, a cache, the model folder or git history."""
    found = sorted({p.name for p in Path(bundle).rglob("*") if p.name in FORBIDDEN or p.name.startswith(".env.")})
    if found:
        raise BundleError(f"the bundle must not hold {', '.join(found)}")


def make_context(dest: Path, repo: Path = REPO_ROOT) -> dict:
    """Writes the bundle into `dest` (new or empty) and returns what it holds, in counts."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise BundleError(f"{dest} isn't empty")
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "HEAD"], check=True,
                             capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    threads = copy_library(repo / "data" / "library", dest / "data" / "library")
    shutil.copy2(repo / "deploy" / "cloudrun" / "Dockerfile", dest / "Dockerfile")
    (dest / ".gcloudignore").write_text("# everything in this bundle is meant for the build\n", encoding="utf-8")
    check_bundle(dest)
    return {"library files": threads, "files": sum(1 for p in dest.rglob("*") if p.is_file())}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    print(make_context(Path(sys.argv[1])))
