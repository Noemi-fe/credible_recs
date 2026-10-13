"""`library add` reading from the archive never reads a thread already saved, nor a gold thread Noemi hasn't labelled
(13 Oct 2026, the data round).

Until now an add through Arctic Shift re-read the threads it had saved before and wrote the archive's copy over the
library's (unless the library's had been read on Reddit), so a second request about the same product gave the same
threads again, written over, instead of new ones. Bright Data's source already skipped them (engine.library.
bright_data_source). Saved threads are kept current by check-live and refresh, not by add, and since Noemi's decision
of 13 Oct 2026 the library keeps only the comments answers use: re-reading a saved thread from the archive would bring
back what the library dropped. The archive's search still finds them; they just aren't chosen or read, so the mix is
made of the next threads in line.

Every test uses fakes and temporary folders with made-up data: no network, nothing written to data/.
"""

from engine import library
from engine.query import parse_query
from engine.sources import ArchiveSource
from engine.tests.test_archive_reader import FakeArchiveClient, kettle_posts
from engine.tests.test_bright_data_source import FakeBrightData
from engine.tests.test_library import FakeParseClient
from engine.tests.test_live_checks import KETTLE, library_of, saved, thread


def test_the_archive_source_leaves_out_the_threads_it_is_told_to_skip():
    client = FakeArchiveClient(kettle_posts())
    threads = ArchiveSource(client, skip_ids={"1a1"}).find_threads(parse_query(KETTLE), limit=2)
    assert [t.id for t in threads] == ["1a2", "1a3"]
    assert "1a1" not in [read for read, _ in client.reads]


def test_the_archive_source_skips_nothing_unless_told():
    threads = ArchiveSource(FakeArchiveClient(kettle_posts())).find_threads(parse_query(KETTLE), limit=2)
    assert [t.id for t in threads] == ["1a1", "1a2"]


def test_command_line_add_through_the_archive_never_reads_or_rewrites_a_saved_thread(tmp_path, capsys):
    folder = library_of(tmp_path, thread("1a1", read_from="arctic_shift"))  # saved before, never checked live
    before = (folder / "threads" / "1a1.json").read_bytes()
    finder = FakeArchiveClient(kettle_posts())
    assert library.main(["add", KETTLE, "--reader", "archive"], client=FakeParseClient(), folder=folder,
                        finder=finder) == 0
    assert "1a1" not in [read for read, _ in finder.reads]
    assert (folder / "threads" / "1a1.json").read_bytes() == before  # the saved copy is untouched
    # The next threads in line take its place in the mix.
    assert [read for read, _ in finder.reads] == ["1a2", "1a3", "1l1", "1w1", "1w2"]
    assert "Saved 5 threads for electric kettle" in capsys.readouterr().out
    assert set(saved(folder)) == {"1a1", "1a2", "1a3", "1l1", "1w1", "1w2"}


def test_command_line_add_through_the_archive_never_reads_an_unlabelled_gold_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "unlabelled_gold_ids", lambda: {"1a2"})
    finder = FakeArchiveClient(kettle_posts())
    assert library.main(["add", KETTLE, "--reader", "archive"], client=FakeParseClient(), folder=tmp_path,
                        finder=finder) == 0
    assert "1a2" not in [read for read, _ in finder.reads]
    assert "1a2" not in saved(tmp_path)


def test_command_line_add_with_the_automatic_reader_skips_saved_threads_in_the_archive_too(tmp_path):
    folder = library_of(tmp_path, thread("1a1", read_from="arctic_shift"))
    finder, bright = FakeArchiveClient(kettle_posts()), FakeBrightData([])
    assert library.main(["add", KETTLE], client=FakeParseClient(), folder=folder, finder=finder,
                        bright_data=bright) == 0
    assert "1a1" not in [read for read, _ in finder.reads]
    assert bright.searches == [] and bright.read == []  # the archive answered: Bright Data never asked
