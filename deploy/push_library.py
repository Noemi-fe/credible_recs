"""Uploads the saved library to Noemi's PRIVATE Hugging Face dataset, for the Space to download when it starts
(deploy/huggingface/DEPLOY.md). Run it by hand, after a library refresh:

    python -m deploy.push_library OWNER/DATASET [--create] [--dry-run] [--library DIR]

What goes up, and nothing else: data/library/threads/*.json, data/library/extracted/*.json and
data/library/profiles.json (the saved threads, what the AI found in them, and writers' standing numbers). The rest of
data/library, data/gold, .env and every cache never do: the files are copied into an empty temporary folder first, and
only that folder is uploaded. A link to a file elsewhere is never followed.

Reddit text only ever goes to a private dataset: just before uploading, the dataset is checked to be private
(repo_info(...).private), and the upload is refused if it isn't. A dataset that doesn't exist yet is created, as
private, only with --create. Threads and extractions no longer in the library (a refresh drops what was deleted on
Reddit) are removed from the dataset in the same commit, so the deletion rule holds there too. --dry-run says what
would happen and changes nothing.

The token is HF_TOKEN, from the environment or .env: a write token (DEPLOY.md, step 2). huggingface_hub is needed
(pip install -e ".[deploy]").
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from engine.library import DEFAULT_LIBRARY_DIR
from engine.parse_reddit import DEFAULT_ENV_FILE as ENV_FILE
from engine.parse_reddit import _read_env_file

FOLDERS = ("threads", "extracted")  # each one's *.json files go up
FILES = ("profiles.json",)
STALE = [f"{folder}/*" for folder in FOLDERS]  # in the dataset, replaced by each upload: what's gone here goes there
TOKEN_VAR = "HF_TOKEN"
_REPO_ID = re.compile(r"[\w.-]+/[\w.-]+")


class LibraryError(ValueError):
    """The library to upload is missing a part; nothing is uploaded then."""


def library_files(library_dir: Path) -> list[tuple[str, Path]]:
    """Every file that goes up, as (its place in the dataset, the file here): each thread's and each extraction's JSON
    file, and profiles.json. Raises LibraryError when any of the three is missing."""
    library_dir = Path(library_dir)
    files = []
    for folder in FOLDERS:
        found = sorted(path for path in (library_dir / folder).glob("*.json")
                       if path.is_file() and not path.is_symlink())
        if not found:
            raise LibraryError(f"Nothing uploaded: there are no {folder}/*.json files in {library_dir}.")
        files += [(f"{folder}/{path.name}", path) for path in found]
    for name in FILES:
        path = library_dir / name
        if not path.is_file() or path.is_symlink():
            raise LibraryError(f"Nothing uploaded: there is no {name} in {library_dir}.")
        files.append((name, path))
    return files


def push_library(api, repo_id: str, library_dir: Path = DEFAULT_LIBRARY_DIR, create: bool = False,
                 dry_run: bool = False, out=print) -> int:
    """Uploads the library to the dataset `repo_id` through `api` (a huggingface_hub.HfApi; the tests give a fake), as
    the module's docstring says. Returns 0 when done (or, for a dry run, when it would be), 1 when refused."""
    try:
        files = library_files(library_dir)
    except LibraryError as error:
        out(str(error))
        return 1
    threads = sum(place.startswith("threads/") for place, _ in files)
    extractions = sum(place.startswith("extracted/") for place, _ in files)
    megabytes = sum(path.stat().st_size for _, path in files) / 1e6
    out(f"The library at {library_dir}: {threads} threads, {extractions} extractions and profiles.json "
        f"({len(files)} files, {megabytes:.1f} MB).")
    if not api.repo_exists(repo_id, repo_type="dataset"):
        if not create:
            out(f"Nothing uploaded: the dataset {repo_id} doesn't exist yet. Create it on huggingface.co as a private "
                "dataset, or run this again with --create to create it, private.")
            return 1
        if dry_run:
            out(f"Dry run: this would create the private dataset {repo_id}, then upload these files. Nothing changed.")
            return 0
        api.create_repo(repo_id, repo_type="dataset", private=True)
        out(f"Created the private dataset {repo_id}.")
    if not api.repo_info(repo_id, repo_type="dataset").private:
        out(f"Refused: the dataset {repo_id} is public, and Reddit text only ever goes to a private one. Make it private "
            "on huggingface.co (the dataset's Settings), then run this again. Nothing was uploaded.")
        return 1
    if dry_run:
        out(f"Dry run: {repo_id} is private, so these files would go up. Nothing was uploaded.")
        return 0
    with tempfile.TemporaryDirectory() as staging:  # only what is copied here can go up
        for place, source in files:
            target = Path(staging) / place
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        api.upload_folder(folder_path=staging, repo_id=repo_id, repo_type="dataset", delete_patterns=STALE,
                          commit_message=f"Library: {threads} threads, {extractions} extractions and profiles")
    out(f"Uploaded to the private dataset {repo_id}. Restart the Space (its Settings) so it downloads the new library.")
    return 0


def _arguments(argv: list[str]) -> tuple[str, bool, bool, Path] | None:
    """(the dataset, --create, --dry-run, --library DIR); None for anything else."""
    repo_ids, create, dry_run, library_dir = [], False, False, DEFAULT_LIBRARY_DIR
    rest = list(argv)
    while rest:
        argument = rest.pop(0)
        if argument == "--create":
            create = True
        elif argument == "--dry-run":
            dry_run = True
        elif argument == "--library" and rest:
            library_dir = Path(rest.pop(0))
        elif argument.startswith("-"):
            return None
        else:
            repo_ids.append(argument)
    if len(repo_ids) != 1 or not _REPO_ID.fullmatch(repo_ids[0]):
        return None
    return repo_ids[0], create, dry_run, library_dir


def _hub_api(token: str):
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit('Uploading needs huggingface_hub: run .venv/bin/pip install -e ".[deploy]" first.')
    return HfApi(token=token)


def main(argv: list[str], make_api=None) -> int:
    arguments = _arguments(argv)
    if arguments is None:
        print(__doc__)
        return 2
    repo_id, create, dry_run, library_dir = arguments
    token = os.environ.get(TOKEN_VAR) or _read_env_file(ENV_FILE).get(TOKEN_VAR)
    if not token:
        print(f"No {TOKEN_VAR}: put the line {TOKEN_VAR}=<your write token> in {ENV_FILE} "
              "(deploy/huggingface/DEPLOY.md, step 2).")
        return 2
    return push_library((make_api or _hub_api)(token), repo_id, library_dir, create=create, dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
