"""Gold-set threads never reach the library (10 Oct 2026).

Noemi labels gold threads herself, and the AI must never read one before she has (anchoring; CLAUDE.md). On 10 Oct
2026 a backup candidate (listed in data/gold/CANDIDATES.md) turned out to be in the library, read and extracted on
9 Oct. So every way into the library now refuses a thread that is in the gold set or on its candidate list: saving
it, reading it through Bright Data into the library, and listing it for the AI to extract. Every id and file here is
made up.
"""

import json

import pytest

from engine import bright_data, extract, library
from engine.gold import GoldThreadError, unlabelled_gold_ids
from engine.tests.factories import make_thread
from engine.models import Thread

CANDIDATES = """# Gold-set candidates

| category | thread | why |
| --- | --- | --- |
| kitchen | [Kettle?](https://www.reddit.com/r/BuyItForLife/comments/1gold01/) (r/BuyItForLife) | classic |
| skincare | [Cleanser?](https://www.reddit.com/r/SkincareAddiction/comments/1gold02/some_title/) | plain |

Backups: [failed first?](https://www.reddit.com/r/BuyItForLife/comments/1gold03/) (kettles).
No longer a backup: 1used01 was read into the library on 9 Oct 2026.
"""


def gold_dir(tmp_path):
    root = tmp_path / "gold"
    (root / "threads").mkdir(parents=True)
    (root / "CANDIDATES.md").write_text(CANDIDATES, encoding="utf-8")
    (root / "threads" / "1gold04.json").write_text("{}", encoding="utf-8")  # saved, not labelled yet
    (root / "threads" / "1gold02.json").write_text("{}", encoding="utf-8")  # saved and labelled (voices.csv)
    (root / "voices.csv").write_text("thread_id,comment_id,voice,tags,note,agrees\n1gold02,c1aaaa,high,recent,,\n",
                                     encoding="utf-8")
    return root


def test_unlabelled_gold_ids_are_the_candidates_and_saved_gold_threads_noemi_hasnt_labelled(tmp_path):
    # Once she has labelled a thread, its copy belongs in the library (CLAUDE.md), so it is no longer refused.
    assert unlabelled_gold_ids(gold_dir(tmp_path)) == {"1gold01", "1gold03", "1gold04"}


def test_without_a_gold_folder_there_are_no_gold_ids(tmp_path):
    assert unlabelled_gold_ids(tmp_path / "nowhere") == set()


def test_the_library_refuses_to_save_a_gold_thread(tmp_path):
    gold = unlabelled_gold_ids(gold_dir(tmp_path))
    thread = Thread.model_validate(make_thread(id="1gold01"))
    with pytest.raises(GoldThreadError) as refused:
        library._save(thread, tmp_path / "library", gold_ids=gold)
    assert "1gold01" in str(refused.value)
    assert not (tmp_path / "library" / "threads" / "1gold01.json").exists()
    other = Thread.model_validate(make_thread(id="1okay01"))
    library._save(other, tmp_path / "library", gold_ids=gold)
    assert (tmp_path / "library" / "threads" / "1okay01.json").exists()


def test_extract_todo_never_lists_a_gold_thread_in_the_library(tmp_path, monkeypatch):
    threads = tmp_path / "library" / "threads"
    threads.mkdir(parents=True)
    for thread_id in ("1gold03", "1gold02", "1okay01"):
        (threads / f"{thread_id}.json").write_text(json.dumps(make_thread(id=thread_id)), encoding="utf-8")
    monkeypatch.setattr(extract, "unlabelled_gold_ids", lambda: unlabelled_gold_ids(gold_dir(tmp_path)))
    assert extract.todo(threads, "extract-v7") == ["1gold02", "1okay01"]  # 1gold02 is labelled


def test_bright_data_refuses_to_read_a_gold_thread_into_the_library(tmp_path, monkeypatch, capsys):
    class NoCalls:
        def get_thread(self, link):
            raise AssertionError("a gold thread must be refused before anything is spent")

        def records_used_this_month(self):
            return 0

    monkeypatch.setattr(bright_data, "unlabelled_gold_ids", lambda: unlabelled_gold_ids(gold_dir(tmp_path)))
    monkeypatch.setattr(bright_data, "LIBRARY_THREADS_DIR", tmp_path / "library" / "threads")
    status = bright_data.main(["fetch", "https://www.reddit.com/r/BuyItForLife/comments/1gold01/",
                               "--to", str(tmp_path / "library" / "threads")], client=NoCalls())
    assert status == 1
    assert "1gold01" in capsys.readouterr().out
