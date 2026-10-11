"""Gets Noemi's Hugging Face Space ready to answer, before the web server starts (deploy/huggingface/start.sh runs it).

1. The saved library (threads, extractions and writers' standing), downloaded from her private dataset
   (CREDIBLE_RECS_LIBRARY_REPO, with the Space secret HF_TOKEN) into data/library, where the engine reads it. It is
   never built into the Space's image: Hugging Face lets anyone run a public Space's image, and the library is Reddit
   text. Without both settings it stops with a plain message, and so it does when the download fails or brings no
   threads: a site that could only fail is worse than one that doesn't start.
2. Module 1's open model, Qwen2.5 1.5B Instruct (a public model, about 1.1 GB), into
   models/qwen2.5-1.5b-instruct/, where engine/query_model.py looks for it. Skipped when CREDIBLE_RECS_QUERY_MODEL is
   "off", or when llama.cpp can't run here. If the download fails the site still starts: module 1 then uses its rules
   alone, as it does whenever the model file isn't there.

    python -m deploy.prepare_space
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_VAR = "HF_TOKEN"  # the Space secret
LIBRARY_REPO_VAR = "CREDIBLE_RECS_LIBRARY_REPO"  # the private dataset holding the library, "owner/name"
MODEL_SWITCH = "CREDIBLE_RECS_QUERY_MODEL"  # "off": module 1 uses its rules alone (engine/query_model.py)
LIBRARY_FOLDER = Path("data") / "library"
LIBRARY_PATTERNS = ["threads/*.json", "extracted/*.json", "profiles.json"]  # what deploy/push_library.py uploads
MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_FOLDER = Path("models") / "qwen2.5-1.5b-instruct"
MODEL_DIR = REPO_ROOT / MODEL_FOLDER


def prepare(environ, root: Path = REPO_ROOT, download_library=None, download_model=None, model_can_run=None,
            out=print) -> int:
    """Downloads the library, then the open model, as the module's docstring says. Returns 0 when the server may start,
    1 when it mustn't. The downloads are huggingface_hub's snapshot_download and hf_hub_download unless given (the tests
    give fakes); `model_can_run` says whether llama.cpp works here."""
    repo_id = environ.get(LIBRARY_REPO_VAR, "").strip()
    token = environ.get(TOKEN_VAR, "").strip()
    if not (repo_id and token):
        out(f"Not starting: this Space needs the secret {TOKEN_VAR} and the variable {LIBRARY_REPO_VAR} (its Settings, "
            "under Variables and secrets; deploy/huggingface/DEPLOY.md, step 7).")
        return 1
    library = Path(root) / LIBRARY_FOLDER
    out(f"Downloading the library from the private dataset {repo_id}...")
    try:
        (download_library or _snapshot_download)(repo_id=repo_id, repo_type="dataset", token=token,
                                                 local_dir=str(library), allow_patterns=LIBRARY_PATTERNS)
    except Exception as error:  # a refused token, a wrong name, no connection: said plainly in the Space's logs
        out(f"Not starting: the library couldn't be downloaded from {repo_id} ({type(error).__name__}: {error}). "
            f"Check that the dataset exists and that {TOKEN_VAR} may read it.")
        return 1
    threads = len(list((library / "threads").glob("*.json")))
    extractions = len(list((library / "extracted").glob("*.json")))
    if not threads:
        out(f"Not starting: the dataset {repo_id} has no threads. Upload the library first, from your computer: "
            f"python -m deploy.push_library {repo_id}")
        return 1
    out(f"Library ready: {threads} threads, {extractions} extractions.")

    if environ.get(MODEL_SWITCH, "").strip().lower() == "off":
        out(f"The open model is switched off ({MODEL_SWITCH}=off): module 1 uses its rules alone.")
        return 0
    if not (model_can_run or llama_cpp_runs)():
        out("llama.cpp can't run here, so the open model isn't downloaded: module 1 uses its rules alone.")
        return 0
    out(f"Downloading the open model ({MODEL_REPO})...")
    try:
        (download_model or _hf_hub_download)(repo_id=MODEL_REPO, filename=MODEL_FILE,
                                             local_dir=str(Path(root) / MODEL_FOLDER), token=False)  # public: no token
    except Exception as error:
        out(f"The open model couldn't be downloaded ({type(error).__name__}): module 1 uses its rules alone.")
        return 0
    out("Open model ready.")
    return 0


def llama_cpp_runs() -> bool:
    """Whether llama.cpp's Python package is installed and its library loads here."""
    try:
        import llama_cpp  # noqa: F401
    except Exception:  # not installed, or its compiled library can't load on this machine
        return False
    return True


def _snapshot_download(**kwargs):
    from huggingface_hub import snapshot_download

    return snapshot_download(**kwargs)


def _hf_hub_download(**kwargs):
    from huggingface_hub import hf_hub_download

    return hf_hub_download(**kwargs)


def main(argv: list[str]) -> int:
    if argv:
        print(__doc__)
        return 2
    return prepare(os.environ)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
