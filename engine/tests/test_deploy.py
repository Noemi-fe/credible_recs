"""Going live (Noemi, 11 Oct 2026): the Hugging Face deployment package (deploy/).

Nothing here reaches the network or Hugging Face: every client is a fake, and no test creates, uploads or downloads
anything for real. The made-up library holds made-up text.
"""

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import prepare_space, push_library
from engine import feedback, web
from engine.parse_reddit import REPO_ROOT

SPACE = REPO_ROOT / "deploy" / "huggingface"
REPO_ID = "noemi-test/credible-recs-library"


def made_up_library(root: Path) -> Path:
    """A library with two threads, their extractions and the profiles, plus files that must never go up."""
    library = root / "library"
    for folder in ("threads", "extracted"):
        (library / folder).mkdir(parents=True)
        for thread_id in ("1fake01", "1fake02"):
            (library / folder / f"{thread_id}.json").write_text(json.dumps({"id": thread_id, "folder": folder}))
    (library / "profiles.json").write_text(json.dumps({"made_up_writer": {"karma": 10}}))
    (library / "candidates.json").write_text("[]")  # the rest of the library stays here
    (library / "requests.jsonl").write_text("{}\n")
    (library / "threads" / "notes.txt").write_text("not a thread")
    (library / "threads" / "older").mkdir()
    (library / "threads" / "older" / "1fake03.json").write_text("{}")
    (root / ".env").write_text("HF_TOKEN=hf_made_up\n")
    (library / "threads" / "sneaky.json").symlink_to(root / ".env")  # a link out of the library is never followed
    return library


class FakeHub:
    """Stands in for huggingface_hub.HfApi: remembers what it was asked; never reaches the network."""

    def __init__(self, exists: bool = True, private: bool = True):
        self.exists = exists
        self.private = private
        self.created: list[dict] = []
        self.uploads: list[dict] = []

    def repo_exists(self, repo_id, repo_type=None, **kwargs):
        assert repo_type == "dataset"
        return self.exists

    def repo_info(self, repo_id, repo_type=None, **kwargs):
        assert repo_type == "dataset" and self.exists
        return SimpleNamespace(id=repo_id, private=self.private)

    def create_repo(self, repo_id, repo_type=None, private=None, **kwargs):
        self.created.append({"repo_id": repo_id, "repo_type": repo_type, "private": private})
        self.exists, self.private = True, bool(private)

    def upload_folder(self, *, folder_path, repo_id, repo_type=None, commit_message=None, delete_patterns=None,
                      **kwargs):
        folder = Path(folder_path)
        files = sorted(str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file())
        self.uploads.append({"files": files, "repo_id": repo_id, "repo_type": repo_type, "message": commit_message,
                             "delete_patterns": delete_patterns, "extra": kwargs,
                             "contents": {name: (folder / name).read_text() for name in files}})


def push(hub: FakeHub, library: Path, **kwargs) -> tuple[int, str]:
    said = []
    code = push_library.push_library(hub, REPO_ID, library, out=said.append, **kwargs)
    return code, "\n".join(said)


# --- deploy/push_library.py: the library goes to the private dataset, and nothing else does ---

def test_only_the_threads_the_extractions_and_the_profiles_go_up(tmp_path):
    hub = FakeHub()
    code, said = push(hub, made_up_library(tmp_path))
    assert code == 0
    (upload,) = hub.uploads
    assert upload["files"] == ["extracted/1fake01.json", "extracted/1fake02.json", "profiles.json",
                               "threads/1fake01.json", "threads/1fake02.json"]
    assert json.loads(upload["contents"]["threads/1fake02.json"]) == {"id": "1fake02", "folder": "threads"}
    assert upload["repo_id"] == REPO_ID and upload["repo_type"] == "dataset"
    assert "5 files" in said


def test_threads_no_longer_in_the_library_are_removed_from_the_dataset_too(tmp_path):
    # A monthly refresh drops what was deleted on Reddit: the dataset loses it in the same commit.
    hub = FakeHub()
    push(hub, made_up_library(tmp_path))
    assert hub.uploads[0]["delete_patterns"] == ["threads/*", "extracted/*"]


def test_a_public_dataset_gets_nothing(tmp_path):
    hub = FakeHub(private=False)
    code, said = push(hub, made_up_library(tmp_path))
    assert code == 1 and hub.uploads == [] and "public" in said


def test_a_missing_dataset_is_created_only_when_asked_and_always_private(tmp_path):
    hub = FakeHub(exists=False)
    code, said = push(hub, made_up_library(tmp_path))
    assert code == 1 and hub.created == [] and hub.uploads == [] and "--create" in said
    code, _ = push(hub, made_up_library(tmp_path / "again"), create=True)
    assert code == 0 and hub.created == [{"repo_id": REPO_ID, "repo_type": "dataset", "private": True}]
    assert len(hub.uploads) == 1


def test_a_dry_run_changes_nothing_and_says_what_would_go_up(tmp_path):
    hub = FakeHub(exists=False)
    code, said = push(hub, made_up_library(tmp_path), create=True, dry_run=True)
    assert code == 0 and hub.created == [] and hub.uploads == []
    assert "2 threads" in said and "2 extractions" in said and "profiles.json" in said
    hub = FakeHub()
    assert push(hub, made_up_library(tmp_path / "again"), dry_run=True)[0] == 0 and hub.uploads == []


@pytest.mark.parametrize("missing", ["threads", "extracted", "profiles.json"])
def test_a_library_missing_a_part_is_never_half_uploaded(tmp_path, missing):
    library = made_up_library(tmp_path)
    target = library / missing
    if target.is_dir():
        for path in target.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
    else:
        target.unlink()
    hub = FakeHub()
    code, said = push(hub, library)
    assert code == 1 and hub.uploads == [] and missing in said


def test_the_command_needs_a_token_and_never_builds_a_client_without_one(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(push_library, "ENV_FILE", tmp_path / "no.env")

    def no_client(token):
        raise AssertionError("no Hugging Face client without a token")

    assert push_library.main([REPO_ID], make_api=no_client) == 2
    assert "HF_TOKEN" in capsys.readouterr().out


def test_the_command_reads_the_token_from_dot_env_and_uploads(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    (tmp_path / ".env").write_text("# made up\nHF_TOKEN=hf_from_dot_env\n")
    monkeypatch.setattr(push_library, "ENV_FILE", tmp_path / ".env")
    library = made_up_library(tmp_path / "data")
    tokens, hub = [], FakeHub()

    def make_api(token):
        tokens.append(token)
        return hub

    assert push_library.main([REPO_ID, "--library", str(library)], make_api=make_api) == 0
    assert tokens == ["hf_from_dot_env"] and len(hub.uploads) == 1


@pytest.mark.parametrize("argv", [[], ["not-a-repo-id"], [REPO_ID, "--force"], [REPO_ID, "other/repo"],
                                  [REPO_ID, "--library"]])
def test_the_command_refuses_anything_it_doesnt_know(argv, capsys):
    assert push_library.main(argv, make_api=lambda token: pytest.fail("nothing should run")) == 2


# --- deploy/prepare_space.py: what the Space does before the server starts ---

SPACE_ENV = {"HF_TOKEN": "hf_made_up", "CREDIBLE_RECS_LIBRARY_REPO": REPO_ID}


class Downloads:
    """Fake downloads: the library one writes a made-up thread and extraction, as the real one would."""

    def __init__(self, threads: int = 2, library_fails: bool = False, model_fails: bool = False):
        self.library_calls: list[dict] = []
        self.model_calls: list[dict] = []
        self.threads = threads
        self.library_fails = library_fails
        self.model_fails = model_fails

    def library(self, **kwargs):
        self.library_calls.append(kwargs)
        if self.library_fails:
            raise PermissionError("401 Unauthorized")
        root = Path(kwargs["local_dir"])
        for folder in ("threads", "extracted"):
            (root / folder).mkdir(parents=True, exist_ok=True)
            for n in range(self.threads):
                (root / folder / f"1fake0{n}.json").write_text("{}")
        return str(root)

    def model(self, **kwargs):
        self.model_calls.append(kwargs)
        if self.model_fails:
            raise ConnectionError("no connection")
        return str(Path(kwargs["local_dir"]) / kwargs["filename"])


def prepare(tmp_path, environ=SPACE_ENV, downloads=None, model_runs=True) -> tuple[int, str, Downloads]:
    downloads = downloads or Downloads()
    said = []
    code = prepare_space.prepare(environ, root=tmp_path, download_library=downloads.library,
                                 download_model=downloads.model, model_can_run=lambda: model_runs, out=said.append)
    return code, "\n".join(said), downloads


@pytest.mark.parametrize("environ", [{}, {"HF_TOKEN": "hf_made_up"}, {"CREDIBLE_RECS_LIBRARY_REPO": REPO_ID},
                                     {"HF_TOKEN": " ", "CREDIBLE_RECS_LIBRARY_REPO": REPO_ID}])
def test_the_space_refuses_to_go_on_without_the_token_and_the_library_dataset(tmp_path, environ):
    code, said, downloads = prepare(tmp_path, environ)
    assert code == 1 and downloads.library_calls == [] and downloads.model_calls == []
    assert "HF_TOKEN" in said and "CREDIBLE_RECS_LIBRARY_REPO" in said


def test_the_space_downloads_the_library_from_the_private_dataset_then_the_model(tmp_path):
    code, said, downloads = prepare(tmp_path)
    assert code == 0
    (library,) = downloads.library_calls
    assert library["repo_id"] == REPO_ID and library["repo_type"] == "dataset" and library["token"] == "hf_made_up"
    assert Path(library["local_dir"]) == tmp_path / "data" / "library"
    assert library["allow_patterns"] == ["threads/*.json", "extracted/*.json", "profiles.json"]
    (model,) = downloads.model_calls
    assert model["repo_id"] == "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    assert model["filename"] == "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    assert Path(model["local_dir"]) == tmp_path / "models" / "qwen2.5-1.5b-instruct"
    assert model["token"] is False  # a public model: Noemi's token isn't sent for it
    assert "2 threads" in said


def test_the_model_lands_exactly_where_module_1_looks_for_it():
    in_repo = Path("models") / "qwen2.5-1.5b-instruct" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    assert prepare_space.MODEL_DIR / prepare_space.MODEL_FILE == REPO_ROOT / in_repo
    query_model = pytest.importorskip("engine.query_model")  # module 1's open model, being built on another branch
    its_repo = Path(query_model.__file__).resolve().parents[1]  # compared within each one's own copy of the repo
    assert query_model.DEFAULT_MODEL_PATH.relative_to(its_repo) == in_repo
    assert query_model.SWITCH == prepare_space.MODEL_SWITCH


@pytest.mark.parametrize("problem", ["library_fails", "no_threads"])
def test_a_library_that_cant_be_had_stops_the_space_with_a_plain_message(tmp_path, problem):
    downloads = Downloads(library_fails=True) if problem == "library_fails" else Downloads(threads=0)
    code, said, downloads = prepare(tmp_path, downloads=downloads)
    assert code == 1 and downloads.model_calls == [] and "Not starting" in said


def test_with_the_model_switched_off_it_isnt_downloaded(tmp_path):
    code, said, downloads = prepare(tmp_path, {**SPACE_ENV, "CREDIBLE_RECS_QUERY_MODEL": "off"})
    assert code == 0 and downloads.model_calls == [] and "rules alone" in said


def test_where_llama_cpp_cant_run_the_model_isnt_downloaded(tmp_path):
    code, said, downloads = prepare(tmp_path, model_runs=False)
    assert code == 0 and downloads.model_calls == [] and "rules alone" in said


def test_a_failed_model_download_still_lets_the_site_start(tmp_path):
    code, said, _ = prepare(tmp_path, downloads=Downloads(model_fails=True))
    assert code == 0 and "rules alone" in said


def test_llama_cpp_that_cant_be_loaded_counts_as_not_running(monkeypatch):
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    assert prepare_space.llama_cpp_runs() is False


# --- The Space's own files: deploy/huggingface/ ---

def front_matter(text: str) -> dict[str, str]:
    block = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL).group(1)
    return dict(line.split(": ", 1) for line in block.splitlines())


def test_the_space_card_says_docker_on_port_7860():
    card = front_matter((SPACE / "README.md").read_text(encoding="utf-8"))
    assert card["sdk"] == "docker" and card["app_port"] == "7860" and card["pinned"] == "false"
    assert card["title"] and card["emoji"] and 0 < len(card["short_description"]) <= 60


def test_the_dockerfile_builds_the_public_code_as_user_1000_and_compiles_nothing():
    dockerfile = (SPACE / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("#") and "\nFROM python:3.12-slim\n" in dockerfile
    assert re.search(r"useradd .*--uid 1000 user", dockerfile) and "\nUSER user\n" in dockerfile
    assert dockerfile.index("USER user") < dockerfile.index("git -C app fetch") < dockerfile.index("pip install")
    assert "ARG CREDIBLE_RECS_REPO=https://github.com/Noemi-fe/credible_recs\n" in dockerfile
    assert "ARG CREDIBLE_RECS_REF=main\n" in dockerfile
    assert '-e ".[deploy]"' in dockerfile
    assert "--only-binary=llama-cpp-python" in dockerfile
    assert "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu" in dockerfile
    assert "EXPOSE 7860" in dockerfile and 'CMD ["sh", "deploy/huggingface/start.sh"]' in dockerfile


def test_nothing_from_this_machine_or_any_secret_goes_into_the_image():
    dockerfile = (SPACE / "Dockerfile").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(COPY|ADD)\b", dockerfile, re.MULTILINE)  # the library is downloaded at start, private
    assert "HF_TOKEN" not in dockerfile and "--mount=type=secret" not in dockerfile


def test_start_gets_the_space_ready_then_starts_the_public_server_on_the_cards_port():
    start = (SPACE / "start.sh").read_text(encoding="utf-8")
    assert start.startswith("#!/bin/sh\n") and "\nset -eu\n" in start
    assert start.index("python -m deploy.prepare_space") < start.index("exec python -m engine.web --public --port 7860")
    # The site answers the Space's own address unless Noemi lists others.
    assert 'CREDIBLE_RECS_ALLOWED_HOSTS="${CREDIBLE_RECS_ALLOWED_HOSTS:-${SPACE_HOST:-}}"' in start


def test_the_guide_names_every_setting_the_code_reads():
    guide = (SPACE / "DEPLOY.md").read_text(encoding="utf-8")
    for name in (feedback.TOKEN_VAR, feedback.REPO_VAR, prepare_space.LIBRARY_REPO_VAR, web.ALLOWED_HOSTS_VAR,
                 web.GOATCOUNTER_VAR, prepare_space.MODEL_SWITCH, "CREDIBLE_RECS_REF"):
        assert name in guide, name
    for command in ("python -m deploy.push_library", "python -m engine.feedback --repo", "--dry-run"):
        assert command in guide, command


def test_huggingface_hub_is_an_optional_extra():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(need.startswith("huggingface_hub") for need in project["optional-dependencies"]["deploy"])
    assert not any("huggingface" in need for need in project["dependencies"])


def test_the_local_demo_runs_without_huggingface_hub():
    script = ("import sys; sys.modules['huggingface_hub'] = None\n"
              "import engine.web, engine.feedback, deploy.push_library, deploy.prepare_space\n"
              "assert isinstance(engine.feedback.store_from_env({}), engine.feedback.LocalStore)")
    done = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
