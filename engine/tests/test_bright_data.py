"""The Bright Data thread reader. Every test uses a fake service, so no test ever touches the network or spends records."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from engine import bright_data
from engine.bright_data import BrightDataClient, BrightDataError, default_env_file, main, save_thread
from engine.config import (
    BRIGHT_DATA_COMMENTS_DATASET as COMMENTS,
    BRIGHT_DATA_MAX_WAIT_SECONDS,
    BRIGHT_DATA_MONTHLY_RECORDS,
    BRIGHT_DATA_POLL_SECONDS,
    BRIGHT_DATA_POSTS_DATASET as POSTS,
)
from engine.models import Thread

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
POST_URL = "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant_for_sensitive_skin/"
COMMENT_LINK = "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/comment/{}/"


def reply(reply_id, text="Same here, it lasted ages.", user="test_replier", replies=None, **extra):
    """One reply as Bright Data nests it inside a comment. All content is made up."""
    item = {
        "reply_id": reply_id, "reply": text, "user_replying": user, "user_url": f"https://www.reddit.com/user/{user}/",
        "date_of_reply": "2025-03-01T11:00:00.000Z", "num_upvotes": 3, "num_replies": len(replies or []),
        "reply_images": [], "replies": replies or [],
    }
    if reply_id is None:
        del item["reply_id"]
    item.update(extra)
    return item


def comment_record(comment_id, text="A readable comment.", user="test_user", replies=None, **extra):
    """One top-level comment record, shaped like the comments dataset's answer. All content is made up."""
    record = {
        "comment_id": comment_id, "url": COMMENT_LINK.format(comment_id), "user_posted": user, "comment": text,
        "date_posted": "2025-03-01T10:00:00.000Z", "num_upvotes": 12, "num_replies": len(replies or []),
        "parent_comment_id": None, "root_comment_id": comment_id, "post_id": "1fake01", "post_url": POST_URL,
        "community_name": "SkincareAddiction", "post_state": "open", "timestamp": "2026-10-09",
        "replies": replies or [],
    }
    record.update(extra)
    return record


def comment_records() -> list[dict]:
    return [
        comment_record(
            "c1aaaa",
            text="  I've used the CeraVe SA Cleanser for 2 years.\n\nGentle, but drying in winter. ",
            replies=[
                reply("c2bbbb", replies=[reply("c3cccc", text="Which size did you get?", date_of_reply="2025-03-02T08:30:00Z")]),
                # Bright Data gave this reply no id: it can't be linked or quoted, and neither can its own reply.
                reply(None, text="A reply with no id.", replies=[reply("c9zzzz")]),
            ],
        ),
        comment_record("c4dddd", text="[deleted]", user="[deleted]", replies=[reply("c5eeee", text="[removed]")]),
        comment_record("c6ffff", text="Still readable; only the account is gone.", user="[deleted]"),
    ]


def post_records() -> list[dict]:
    return [{
        "post_id": "1fake01", "url": POST_URL, "user_posted": "test_op", "title": "Gentle exfoliant for sensitive skin?",
        "description": "Looking for something under £30.", "num_upvotes": 150, "num_comments": 42,
        "date_posted": "2025-03-01T09:00:00.000Z", "community_name": "SkincareAddiction",
    }]


class FakeBrightData:
    """Stands in for Bright Data: starts jobs, reports their progress and hands over their records.

    `progress[dataset]` is the list of statuses the progress check answers in turn (the last one repeats);
    `answers[(step, dataset)]` replaces one step's answer with (status, body), step being trigger, progress or snapshot.
    """

    def __init__(self, comments=None, post=None, progress=None, answers=None):
        self.records = {COMMENTS: comment_records() if comments is None else comments,
                        POSTS: post_records() if post is None else post}
        self.progress = {COMMENTS: ["running", "ready"], POSTS: ["ready"], **(progress or {})}
        self.answers = answers or {}
        self.requests = []
        self.jobs = {}  # snapshot id -> [dataset, progress checks so far]

    def __call__(self, method, url, headers, data=None):
        self.requests.append((method, url, headers, data))
        path = urlparse(url).path
        if path.endswith("/trigger"):
            dataset = parse_qs(urlparse(url).query)["dataset_id"][0]
            snapshot_id = f"s_{dataset[-4:]}_{len(self.jobs) + 1}"
            self.jobs[snapshot_id] = [dataset, 0]
            return self._answer("trigger", dataset, {"snapshot_id": snapshot_id})
        snapshot_id = path.rstrip("/").rsplit("/", 1)[1]
        dataset, checks = self.jobs[snapshot_id]
        if "/progress/" in path:
            self.jobs[snapshot_id][1] += 1
            statuses = self.progress[dataset]
            return self._answer("progress", dataset, {"status": statuses[min(checks, len(statuses) - 1)], "snapshot_id": snapshot_id})
        return self._answer("snapshot", dataset, self.records[dataset])

    def _answer(self, step, dataset, body):
        status, body = self.answers.get((step, dataset), (200, body))
        return status, body if isinstance(body, bytes) else json.dumps(body).encode()

    def triggered(self) -> list[str]:
        """The datasets of the jobs started, in order."""
        return [parse_qs(urlparse(url).query)["dataset_id"][0] for _, url, _, _ in self.requests if "/trigger" in url]


class FakeClock:
    def __init__(self):
        self.now = NOW
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def make_client(tmp_path, service=None, clock=None, api_key="test-key", offline=False):
    clock = clock or FakeClock()
    return BrightDataClient(
        api_key=api_key, cache_dir=tmp_path / "cache", fetch=service or FakeBrightData(), clock=clock, sleep=clock.sleep,
        offline=offline,
    )


def write_usage(client, records, at=NOW):
    client.usage_log.parent.mkdir(parents=True, exist_ok=True)
    with client.usage_log.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": at.isoformat(), "dataset": "comments", "snapshot_id": "s_old", "records": records}) + "\n")


# --- Turning Bright Data's records into our Thread shape ---

def test_thread_is_mapped_into_our_shape(tmp_path):
    clock = FakeClock()
    thread = make_client(tmp_path, clock=clock).get_thread(POST_URL)
    assert (thread.id, thread.community, thread.category, thread.source) == ("1fake01", "SkincareAddiction", "skincare", "reddit")
    assert (thread.title, thread.body, thread.author.name) == ("Gentle exfoliant for sensitive skin?", "Looking for something under £30.", "test_op")
    assert (thread.score, thread.num_comments) == (150, 42)
    assert thread.created_at == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
    assert thread.url == POST_URL
    assert thread.collected_at == clock.now  # when the comments were downloaded


def test_nested_replies_are_flattened_in_thread_order(tmp_path):
    thread = make_client(tmp_path).get_thread(POST_URL)
    assert [c.id for c in thread.comments] == ["c1aaaa", "c2bbbb", "c3cccc", "c4dddd", "c5eeee", "c6ffff"]


def test_replies_point_to_the_comment_they_are_nested_in(tmp_path):
    parents = {c.id: c.parent_id for c in make_client(tmp_path).get_thread(POST_URL).comments}
    assert parents == {"c1aaaa": None, "c2bbbb": "c1aaaa", "c3cccc": "c2bbbb", "c4dddd": None, "c5eeee": "c4dddd", "c6ffff": None}


def test_the_read_more_button_is_not_part_of_the_post_text(tmp_path):
    # Seen on 9 Oct 2026: the post's text came back exactly as written, then " Read more", the label of Reddit's button.
    post = post_records()[0] | {"description": "Looking for something under £30.\n\nThanks! Read more"}
    thread = make_client(tmp_path, FakeBrightData(post=[post])).get_thread(POST_URL)
    assert thread.body == "Looking for something under £30.\n\nThanks!"


def test_dates_are_kept_to_the_second_as_reddit_gives_them(tmp_path):
    # Seen on 9 Oct 2026: the post's date came with milliseconds that Reddit's own dates don't have.
    post = post_records()[0] | {"date_posted": "2025-03-01T09:00:00.258Z"}
    thread = make_client(tmp_path, FakeBrightData(post=[post])).get_thread(POST_URL)
    assert thread.created_at == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)


def test_comment_text_is_kept_exactly(tmp_path):
    thread = make_client(tmp_path).get_thread(POST_URL)
    assert thread.comments[0].body == "  I've used the CeraVe SA Cleanser for 2 years.\n\nGentle, but drying in winter. "


def test_dates_scores_and_writers_of_replies(tmp_path):
    comments = {c.id: c for c in make_client(tmp_path).get_thread(POST_URL).comments}
    assert comments["c1aaaa"].created_at == datetime(2025, 3, 1, 10, 0, tzinfo=UTC)
    assert comments["c3cccc"].created_at == datetime(2025, 3, 2, 8, 30, tzinfo=UTC)
    assert (comments["c2bbbb"].score, comments["c2bbbb"].author.name) == (3, "test_replier")


def test_deleted_and_removed_comments(tmp_path):
    comments = {c.id: c for c in make_client(tmp_path).get_thread(POST_URL).comments}
    assert (comments["c4dddd"].status, comments["c4dddd"].author) == ("deleted", None)
    assert comments["c5eeee"].status == "removed"
    assert (comments["c6ffff"].status, comments["c6ffff"].author) == ("ok", None)


def test_comment_links_end_with_the_comment_id(tmp_path):
    # The live check reads the comment named at the end of its link, so a reply's link is built when Bright Data gives none.
    comments = {c.id: c for c in make_client(tmp_path).get_thread(POST_URL).comments}
    assert comments["c1aaaa"].url == COMMENT_LINK.format("c1aaaa")
    assert comments["c2bbbb"].url == COMMENT_LINK.format("c2bbbb")  # not the writer's profile link (user_url)


def test_a_record_link_that_is_not_the_comments_own_is_replaced(tmp_path):
    service = FakeBrightData(comments=[comment_record("c1aaaa", url=POST_URL)])
    comment = make_client(tmp_path, service).get_thread(POST_URL).comments[0]
    assert comment.url == COMMENT_LINK.format("c1aaaa")


def test_a_reply_with_no_id_is_kept_out_with_its_replies_and_counted(tmp_path):
    client = make_client(tmp_path)
    thread = client.get_thread(POST_URL)
    assert "c9zzzz" not in {c.id for c in thread.comments}
    assert client.last_read.left_out == 2


def test_reddit_type_prefixes_are_dropped_and_a_parent_that_is_the_post_means_top_level(tmp_path):
    record = comment_record("t1_c1aaaa", parent_comment_id="t3_1fake01", replies=[reply("t1_c2bbbb")])
    comments = make_client(tmp_path, FakeBrightData(comments=[record])).get_thread(POST_URL).comments
    assert [(c.id, c.parent_id) for c in comments] == [("c1aaaa", None), ("c2bbbb", "c1aaaa")]


def test_replies_nested_under_another_field_name_are_found_and_images_are_not_replies(tmp_path):
    deeper = reply("c2bbbb", replies=[], reply_images=[{"url": "https://i.example.invalid/a.jpg"}], more_replies=[reply("c3cccc")])
    comments = make_client(tmp_path, FakeBrightData(comments=[comment_record("c1aaaa", replies=[deeper])])).get_thread(POST_URL).comments
    assert [(c.id, c.parent_id) for c in comments] == [("c1aaaa", None), ("c2bbbb", "c1aaaa"), ("c3cccc", "c2bbbb")]


def test_a_comment_with_no_text_is_kept_for_its_replies_but_has_nothing_to_quote(tmp_path):
    record = comment_record("c1aaaa", text=None, replies=[reply("c2bbbb")])
    comments = make_client(tmp_path, FakeBrightData(comments=[record])).get_thread(POST_URL).comments
    assert [(c.id, c.status, c.body) for c in comments] == [("c1aaaa", "deleted", ""), ("c2bbbb", "ok", "Same here, it lasted ages.")]


def test_a_comment_with_no_readable_date_is_kept_out_and_counted(tmp_path):
    client = make_client(tmp_path, FakeBrightData(comments=[comment_record("c1aaaa", date_posted="soon"), comment_record("c2bbbb")]))
    assert [c.id for c in client.get_thread(POST_URL).comments] == ["c2bbbb"]
    assert client.last_read.left_out == 1


def test_a_comment_given_twice_is_kept_once(tmp_path):
    records = [comment_record("c1aaaa", replies=[reply("c2bbbb")]), comment_record("c2bbbb")]
    comments = make_client(tmp_path, FakeBrightData(comments=records)).get_thread(POST_URL).comments
    assert [(c.id, c.parent_id) for c in comments] == [("c1aaaa", None), ("c2bbbb", "c1aaaa")]


def test_error_records_are_skipped(tmp_path):
    records = comment_records() + [{"error": "Page not reachable", "error_code": "dead_page", "input": {"url": POST_URL}}]
    client = make_client(tmp_path, FakeBrightData(comments=records))
    assert len(client.get_thread(POST_URL).comments) == 6


def test_a_thread_built_from_bright_data_saves_and_loads_as_a_thread(tmp_path):
    thread = make_client(tmp_path).get_thread(POST_URL)
    path = save_thread(thread, tmp_path / "threads")
    assert path == tmp_path / "threads" / "1fake01.json"
    assert Thread.model_validate_json(path.read_text(encoding="utf-8")) == thread
    with pytest.raises(FileExistsError):
        save_thread(thread, tmp_path / "threads")


# --- When the post itself can't be read ---

def test_when_the_post_job_fails_the_title_comes_from_the_link(tmp_path):
    client = make_client(tmp_path, FakeBrightData(progress={POSTS: ["failed"]}))
    thread = client.get_thread(POST_URL)
    assert thread.title == "gentle exfoliant for sensitive skin"
    assert (thread.body, thread.author, thread.score) == ("", None, 0)
    assert thread.num_comments == len(thread.comments) == 6
    assert thread.created_at == datetime(2025, 3, 1, 10, 0, tzinfo=UTC)  # the earliest comment: the post is no later
    assert client.last_read.post_read is False
    assert "title" in client.last_read.post_note


def test_when_the_post_answer_holds_only_an_error_the_title_comes_from_the_link(tmp_path):
    client = make_client(tmp_path, FakeBrightData(post=[{"error": "Post not found", "input": {"url": POST_URL}}]))
    assert client.get_thread(POST_URL).title == "gentle exfoliant for sensitive skin"
    assert "Post not found" in client.last_read.post_note


def test_a_link_without_a_title_part_takes_it_from_the_comment_records(tmp_path):
    service = FakeBrightData(progress={POSTS: ["failed"]})
    thread = make_client(tmp_path, service).get_thread("https://www.reddit.com/r/SkincareAddiction/comments/1fake01/")
    assert thread.title == "gentle exfoliant for sensitive skin"


def test_comments_are_never_reported_missing_when_bright_data_returns_none(tmp_path):
    # An empty answer must not look like a thread whose comments were all deleted.
    with pytest.raises(BrightDataError, match="no comments"):
        make_client(tmp_path, FakeBrightData(comments=[])).get_thread(POST_URL)


def test_only_error_records_for_the_comments_is_an_error(tmp_path):
    service = FakeBrightData(comments=[{"error": "Page not reachable", "input": {"url": POST_URL}}])
    with pytest.raises(BrightDataError, match="Page not reachable"):
        make_client(tmp_path, service).get_thread(POST_URL)


# --- Jobs: start, wait, download ---

def test_the_post_is_read_first_then_its_comments(tmp_path):
    service = FakeBrightData()
    make_client(tmp_path, service).get_thread(POST_URL)
    assert service.triggered() == [POSTS, COMMENTS]


def test_a_job_is_started_with_the_key_and_the_thread_link(tmp_path):
    service = FakeBrightData()
    make_client(tmp_path, service).get_thread("https://old.reddit.com/r/skincareaddiction/comments/1fake01/gentle_exfoliant_for_sensitive_skin/c1aaaa/?context=3")
    method, url, headers, data = next(r for r in service.requests if f"dataset_id={COMMENTS}" in r[1])
    assert method == "POST"
    assert url.startswith("https://api.brightdata.com/datasets/v3/trigger?") and "include_errors=true" in url
    assert headers["Authorization"] == "Bearer test-key"
    assert json.loads(data) == [{"url": "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant_for_sensitive_skin/"}]


def test_progress_is_asked_every_poll_interval_until_ready(tmp_path):
    clock = FakeClock()
    service = FakeBrightData(progress={COMMENTS: ["starting", "running", "running", "ready"]})
    make_client(tmp_path, service, clock).get_thread(POST_URL)
    assert clock.slept == [BRIGHT_DATA_POLL_SECONDS] * 5  # one for the post, four for the comments
    assert any("/snapshot/" in url and "format=json" in url for _, url, _, _ in service.requests)


def test_a_failed_job_is_an_error(tmp_path):
    with pytest.raises(BrightDataError, match="failed"):
        make_client(tmp_path, FakeBrightData(progress={COMMENTS: ["running", "failed"]})).get_thread(POST_URL)


def test_a_job_that_takes_too_long_is_an_error_and_is_picked_up_next_time(tmp_path):
    clock = FakeClock()
    service = FakeBrightData(progress={COMMENTS: ["running"]})
    with pytest.raises(BrightDataError, match="longer than"):
        make_client(tmp_path, service, clock).get_thread(POST_URL)
    assert sum(clock.slept) <= BRIGHT_DATA_MAX_WAIT_SECONDS + 2 * BRIGHT_DATA_POLL_SECONDS
    service.progress[COMMENTS] = ["ready"]
    thread = make_client(tmp_path, service, clock).get_thread(POST_URL)
    assert len(thread.comments) == 6
    assert service.triggered() == [POSTS, COMMENTS]  # the slow job was downloaded, not paid for twice


def test_a_job_bright_data_no_longer_knows_counts_as_failed_and_is_not_picked_up_again(tmp_path):
    service = FakeBrightData(answers={("progress", COMMENTS): (404, {"error": "Snapshot not found"})})
    with pytest.raises(BrightDataError, match="failed"):
        make_client(tmp_path, service).get_thread(POST_URL)
    del service.answers[("progress", COMMENTS)]
    make_client(tmp_path, service).get_thread(POST_URL)
    assert service.triggered() == [POSTS, COMMENTS, COMMENTS]


def test_a_progress_check_that_gets_no_answer_is_asked_again(tmp_path):
    service = FakeBrightData()
    answers = iter([BrightDataError("couldn't reach Bright Data: timed out")])

    def flaky(method, url, headers, data=None):
        if "/progress/" in url and (trouble := next(answers, None)):
            raise trouble
        return service(method, url, headers, data)

    assert len(make_client(tmp_path, flaky).get_thread(POST_URL).comments) == 6


def test_a_snapshot_still_being_built_is_asked_again(tmp_path):
    service = FakeBrightData()
    original = service._answer
    building = iter([(202, {"status": "building", "message": "Snapshot is building, try again in 10s"})])

    def answer(step, dataset, body):
        if step == "snapshot" and dataset == COMMENTS and (early := next(building, None)):
            return early[0], json.dumps(early[1]).encode()
        return original(step, dataset, body)

    service._answer = answer
    assert len(make_client(tmp_path, service).get_thread(POST_URL).comments) == 6


# --- Errors never crash a caller ---

def test_a_refused_key_is_reported_and_stops_everything(tmp_path):
    service = FakeBrightData(answers={("trigger", POSTS): (401, {"error": "Unauthorized"})})
    with pytest.raises(BrightDataError, match="BRIGHT_DATA_API_KEY") as caught:
        make_client(tmp_path, service).get_thread(POST_URL)
    assert caught.value.account_problem
    assert service.triggered() == [POSTS]  # the comments job wasn't tried with a bad key


def test_running_out_of_records_is_reported(tmp_path):
    service = FakeBrightData(answers={("trigger", COMMENTS): (402, {"error": "Monthly quota exceeded"})})
    with pytest.raises(BrightDataError, match="quota") as caught:
        make_client(tmp_path, service).get_thread(POST_URL)
    assert caught.value.account_problem


@pytest.mark.parametrize("step, answer", [
    ("trigger", (200, {"message": "accepted"})),  # no snapshot id
    ("snapshot", (200, {"records": "not a list"})),
    ("snapshot", (200, b"<html>Bad gateway</html>")),
    ("snapshot", (500, {"error": "internal"})),
])
def test_unreadable_answers_are_errors(tmp_path, step, answer):
    with pytest.raises(BrightDataError):
        make_client(tmp_path, FakeBrightData(answers={(step, COMMENTS): answer})).get_thread(POST_URL)


@pytest.mark.parametrize("trouble", [TimeoutError("The read operation timed out"), __import__("urllib.error").error.URLError("no route")])
def test_a_network_failure_is_a_bright_data_error_not_a_crash(monkeypatch, trouble):
    import urllib.request

    def fail(*args, **kwargs):
        raise trouble

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(BrightDataError, match="couldn't reach Bright Data"):
        bright_data._http("GET", "https://api.example.invalid/", {})


def test_a_subreddit_outside_the_decided_list_spends_nothing(tmp_path):
    service = FakeBrightData()
    with pytest.raises(ValueError, match="AskReddit"):
        make_client(tmp_path, service).get_thread("https://www.reddit.com/r/AskReddit/comments/1fake01/x/")
    assert service.requests == []


# --- The key ---

def test_missing_key_is_explained_and_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIGHT_DATA_API_KEY", raising=False)
    service = FakeBrightData()
    client = BrightDataClient(cache_dir=tmp_path / "cache", fetch=service, env_file=tmp_path / "missing.env")
    with pytest.raises(BrightDataError, match="BRIGHT_DATA_API_KEY"):
        client.get_thread(POST_URL)
    assert service.requests == []


def test_key_is_read_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BRIGHT_DATA_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("PARSE_API_KEY=other\nBRIGHT_DATA_API_KEY=key-from-file\n")
    service = FakeBrightData()
    clock = FakeClock()
    BrightDataClient(cache_dir=tmp_path / "cache", fetch=service, env_file=env_file, clock=clock, sleep=clock.sleep).get_thread(POST_URL)
    assert service.requests[0][2]["Authorization"] == "Bearer key-from-file"


def test_a_git_worktree_without_its_own_env_file_uses_the_main_checkouts(tmp_path):
    main_checkout, worktree = tmp_path / "project", tmp_path / "worktrees" / "branch"
    (main_checkout / ".git" / "worktrees" / "branch").mkdir(parents=True)
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {main_checkout / '.git' / 'worktrees' / 'branch'}\n")
    assert default_env_file(worktree) == main_checkout / ".env"
    (worktree / ".env").write_text("BRIGHT_DATA_API_KEY=own\n")
    assert default_env_file(worktree) == worktree / ".env"
    assert default_env_file(main_checkout) == main_checkout / ".env"


def test_the_key_is_never_saved_in_the_cache_or_the_log(tmp_path):
    client = make_client(tmp_path, api_key="secret-test-key-123")
    client.get_thread(POST_URL)
    for path in (tmp_path / "cache").rglob("*"):
        if path.is_file():
            assert "secret-test-key-123" not in path.read_text(encoding="utf-8")


def test_an_answer_that_repeats_the_key_never_shows_it_in_the_error(tmp_path):
    service = FakeBrightData(answers={("trigger", POSTS): (401, {"error": "Invalid token secret-test-key-123"})})
    with pytest.raises(BrightDataError) as caught:
        make_client(tmp_path, service, api_key="secret-test-key-123").get_thread(POST_URL)
    assert "secret-test-key-123" not in str(caught.value)


# --- Records: the usage log and the monthly budget ---

def test_every_record_delivered_is_logged(tmp_path):
    client = make_client(tmp_path)
    client.get_thread(POST_URL)
    assert client.records_used_this_month() == 1 + 3  # one post, three top-level comment records


def test_records_from_last_month_do_not_count(tmp_path):
    client = make_client(tmp_path)
    write_usage(client, 4000, at=NOW - timedelta(days=31))
    assert client.records_used_this_month() == 0


def test_a_job_that_could_go_past_the_monthly_records_is_refused(tmp_path):
    # The post says 42 comments: its comments job could cost up to 42 records.
    service = FakeBrightData()
    client = make_client(tmp_path, service)
    write_usage(client, BRIGHT_DATA_MONTHLY_RECORDS - 42)
    with pytest.raises(BrightDataError, match="records") as caught:
        client.get_thread(POST_URL)
    assert not caught.value.account_problem  # a smaller thread could still fit in what is left
    assert service.triggered() == [POSTS]


def test_with_no_records_left_nothing_is_started(tmp_path):
    service = FakeBrightData()
    client = make_client(tmp_path, service)
    write_usage(client, BRIGHT_DATA_MONTHLY_RECORDS)
    with pytest.raises(BrightDataError, match="records"):
        client.get_thread(POST_URL)
    assert service.requests == []


# --- The cache (the deletion rule) and offline use ---

def test_second_request_comes_from_the_cache(tmp_path):
    service = FakeBrightData()
    client = make_client(tmp_path, service)
    first = client.get_thread(POST_URL)
    count = len(service.requests)
    assert client.get_thread(POST_URL) == first
    assert len(service.requests) == count
    assert client.records_used_this_month() == 4


def test_cache_expires_after_48_hours(tmp_path):
    service, clock = FakeBrightData(), FakeClock()
    make_client(tmp_path, service, clock).get_thread(POST_URL)
    clock.now += timedelta(hours=49)
    make_client(tmp_path, service, clock).get_thread(POST_URL)
    assert service.triggered() == [POSTS, COMMENTS, POSTS, COMMENTS]


def test_old_cache_entries_are_deleted(tmp_path):
    clock = FakeClock()
    make_client(tmp_path, clock=clock).get_thread(POST_URL)
    assert list((tmp_path / "cache" / "responses").glob("*.json"))
    clock.now += timedelta(hours=49)
    make_client(tmp_path, clock=clock)
    assert not list((tmp_path / "cache" / "responses").glob("*.json"))


def test_offline_client_answers_from_its_cache_and_never_spends(tmp_path):
    service = FakeBrightData()
    make_client(tmp_path, service).get_thread(POST_URL)
    count = len(service.requests)
    offline = make_client(tmp_path, service, offline=True)
    assert offline.get_thread(POST_URL).id == "1fake01"
    with pytest.raises(BrightDataError, match="offline"):
        offline.get_thread("https://www.reddit.com/r/SkincareAddiction/comments/1other2/another/")
    assert len(service.requests) == count


# --- Command line ---

def test_fetch_saves_the_thread_and_reports_counts_only(tmp_path, capsys):
    client = make_client(tmp_path)
    assert main(["fetch", POST_URL, "--to", str(tmp_path / "threads")], client=client) == 0
    saved = Thread.model_validate_json((tmp_path / "threads" / "1fake01.json").read_text(encoding="utf-8"))
    assert len(saved.comments) == 6
    printed = capsys.readouterr().out
    assert "6 comments" in printed and "records used this month: 4" in printed
    assert "CeraVe" not in printed and "test_user" not in printed  # never comment text or names


def test_fetch_says_when_fewer_comments_arrived_than_reddit_counts(tmp_path, capsys):
    # The post says 42 comments and 6 arrive: seen for real on 9 Oct 2026, when replies to replies were left out.
    main(["fetch", POST_URL, "--to", str(tmp_path / "threads")], client=make_client(tmp_path))
    assert "Reddit counts 42 comments; 6 arrived" in capsys.readouterr().out


def test_fetch_skips_a_thread_already_saved_without_spending(tmp_path, capsys):
    service = FakeBrightData()
    folder = tmp_path / "threads"
    folder.mkdir()
    (folder / "1fake01.json").write_text("{}")
    assert main(["fetch", POST_URL, "--to", str(folder)], client=make_client(tmp_path, service)) == 0
    assert service.requests == []
    assert "already" in capsys.readouterr().out


def test_fetch_reports_an_error_without_crashing(tmp_path, capsys):
    service = FakeBrightData(answers={("trigger", POSTS): (401, {"error": "Unauthorized"})})
    assert main(["fetch", POST_URL, "--to", str(tmp_path / "threads")], client=make_client(tmp_path, service)) == 1
    assert "BRIGHT_DATA_API_KEY" in capsys.readouterr().out


def test_usage_prints_the_records_used(tmp_path, capsys):
    client = make_client(tmp_path)
    write_usage(client, 17)
    assert main(["usage"], client=client) == 0
    assert f"17 of {BRIGHT_DATA_MONTHLY_RECORDS}" in capsys.readouterr().out


def test_fetch_by_default_saves_outside_the_project():
    # A trial read must not land in the library or the gold set: those are filled by their own commands.
    assert not bright_data.DEFAULT_THREADS_DIR.is_relative_to(bright_data.REPO_ROOT)


def test_a_thread_read_through_bright_data_says_so_and_counts_as_read_on_reddit(tmp_path):
    # Bright Data reads Reddit as it is now, so its threads are checked live when read (9 Oct 2026).
    clock = FakeClock()
    thread = make_client(tmp_path, clock=clock).get_thread(POST_URL)
    assert thread.read_from == "bright_data" and thread.last_checked_live() == clock.now


# --- Discovery: finding threads with Reddit's search, through Bright Data ---

def found_record(post_id, title="Best gentle cleanser for acne-prone skin?", community="SkincareAddiction", comments=40, **extra):
    """One post as the discovery job returns it: the whole post, text and first comments included. All made up."""
    record = {
        "post_id": f"t3_{post_id}", "url": f"https://www.reddit.com/r/{community}/comments/{post_id}/x/", "title": title,
        "community_name": community, "num_comments": comments, "num_upvotes": 25, "date_posted": "2025-05-01T09:00:00.000Z",
        "description": "The post's own text, never kept.", "user_posted": "test_op",
        "comments": [{"comment": "A first comment, never kept.", "user_commenting": "test_user"}],
        "discovery_input": {"keyword": "subreddit:SkincareAddiction gentle cleanser"},
    }
    record.update(extra)
    return record


def discovery_service(records=None, **kwargs):
    found = [found_record("1aaaa01"), found_record("1aaaa02", title="Cleanser that won't strip my skin", comments=12)]
    return FakeBrightData(post=found if records is None else records, progress={POSTS: ["running", "ready"]}, **kwargs)


def test_discover_lists_the_posts_found_with_ids_titles_and_comment_counts(tmp_path):
    found = make_client(tmp_path, discovery_service()).discover([("SkincareAddiction", "gentle cleanser")], posts_each=5)
    assert [(f.id, f.subreddit, f.title, f.num_comments) for f in found] == [
        ("1aaaa01", "SkincareAddiction", "Best gentle cleanser for acne-prone skin?", 40),
        ("1aaaa02", "SkincareAddiction", "Cleanser that won't strip my skin", 12),
    ]
    assert found[0].created_at == datetime(2025, 5, 1, 9, 0, tzinfo=UTC)
    assert found[0].url == "https://www.reddit.com/r/SkincareAddiction/comments/1aaaa01/"


def test_discover_asks_reddits_search_within_each_subreddit_in_one_job(tmp_path):
    service = discovery_service()
    make_client(tmp_path, service).discover([("SkincareAddiction", "gentle cleanser"), ("r/castiron", "first skillet")], posts_each=5)
    triggers = [(url, body) for method, url, _, body in service.requests if "/trigger" in url]
    assert len(triggers) == 1
    params = parse_qs(urlparse(triggers[0][0]).query)
    assert params["dataset_id"] == [POSTS] and params["type"] == ["discover_new"] and params["discover_by"] == ["keyword"]
    assert json.loads(triggers[0][1]) == [
        {"keyword": "subreddit:SkincareAddiction gentle cleanser", "date": "All time", "num_of_posts": 5, "sort_by": "Relevance"},
        {"keyword": "subreddit:castiron first skillet", "date": "All time", "num_of_posts": 5, "sort_by": "Relevance"},
    ]


def test_discover_keeps_only_posts_from_the_subreddits_asked_each_once_and_no_error_records(tmp_path):
    records = [
        found_record("1aaaa01"),
        found_record("1aaaa01"),  # found by two searches
        found_record("1bbbb01", community="acne"),  # Reddit's search can stray outside the subreddit
        {"error": "page not found", "error_code": "dead_page"},
        found_record("1cccc01", community="skincareaddiction"),  # Reddit's spelling may differ in case
    ]
    found = make_client(tmp_path, discovery_service(records)).discover([("SkincareAddiction", "cleanser")], posts_each=5)
    assert [(f.id, f.subreddit) for f in found] == [("1aaaa01", "SkincareAddiction"), ("1cccc01", "SkincareAddiction")]


def test_discover_refuses_a_subreddit_outside_the_decided_list_before_spending(tmp_path):
    service = discovery_service()
    with pytest.raises(ValueError, match="AskReddit"):
        make_client(tmp_path, service).discover([("SkincareAddiction", "cleanser"), ("AskReddit", "cleanser")], posts_each=5)
    assert service.requests == []


def test_discover_is_refused_when_it_could_go_past_the_months_records(tmp_path):
    service = discovery_service()
    client = make_client(tmp_path, service)
    write_usage(client, BRIGHT_DATA_MONTHLY_RECORDS - 9)
    with pytest.raises(BrightDataError, match="monthly"):
        client.discover([("SkincareAddiction", "cleanser"), ("AsianBeauty", "cleanser")], posts_each=5)
    assert service.requests == []


def test_discover_logs_every_record_delivered_and_asking_again_comes_from_the_cache(tmp_path):
    records = [found_record("1aaaa01"), found_record("1bbbb01", community="acne"), {"error": "page not found"}]
    service = discovery_service(records)
    client = make_client(tmp_path, service)
    first = client.discover([("SkincareAddiction", "cleanser")], posts_each=5)
    assert client.records_used_this_month() == 3  # every record delivered is paid for, even those left out
    assert client.discover([("SkincareAddiction", "cleanser")], posts_each=5) == first
    assert len([r for r in service.requests if "/trigger" in r[1]]) == 1
    assert client.records_used_this_month() == 3


def test_discover_keeps_no_post_text_comments_or_writers(tmp_path):
    client = make_client(tmp_path, discovery_service())
    client.discover([("SkincareAddiction", "cleanser")], posts_each=5)
    for path in (tmp_path / "cache").rglob("*"):
        if path.is_file():
            saved = path.read_text(encoding="utf-8")
            assert "never kept" not in saved and "test_op" not in saved and "test_user" not in saved


def test_discover_needs_at_least_one_search_and_a_sensible_number_of_posts(tmp_path):
    client = make_client(tmp_path, discovery_service())
    with pytest.raises(ValueError):
        client.discover([], posts_each=5)
    with pytest.raises(ValueError):
        client.discover([("SkincareAddiction", "cleanser")], posts_each=0)
    with pytest.raises(ValueError):
        client.discover([("SkincareAddiction", "  ")], posts_each=5)


def test_discover_command_prints_ids_titles_comment_counts_and_records_used(tmp_path, capsys):
    client = make_client(tmp_path, discovery_service())
    assert main(["discover", "--posts", "5", "SkincareAddiction", "gentle cleanser"], client=client) == 0
    printed = capsys.readouterr().out
    assert "1aaaa01" in printed and "Best gentle cleanser for acne-prone skin?" in printed and "40 comments" in printed
    assert "records used this month: 2" in printed
    assert "never kept" not in printed and "test_op" not in printed and "test_user" not in printed


def test_discover_command_needs_pairs_of_subreddit_and_words(tmp_path, capsys):
    service = discovery_service()
    assert main(["discover", "SkincareAddiction"], client=make_client(tmp_path, service)) == 2
    assert main(["discover", "--posts", "x", "SkincareAddiction", "cleanser"], client=make_client(tmp_path, service)) == 2
    assert service.requests == []


def test_discover_command_reports_a_refused_subreddit_without_crashing(tmp_path, capsys):
    service = discovery_service()
    assert main(["discover", "AskReddit", "cleanser"], client=make_client(tmp_path, service)) == 1
    assert "AskReddit" in capsys.readouterr().out and service.requests == []


# --- Reading several threads at once (11 Oct 2026) ---
# One thread at a time costs two jobs, about 2.5 minutes (the add of 11 Oct 2026 took 12.5 minutes for 2 threads), so a
# monthly refresh of the library would take hours. prefetch reads a batch of threads in two jobs (their posts, then
# their comments) and files each thread's records in its own cache entry, where get_thread finds them.

from engine.parse_reddit import parse_thread_url  # noqa: E402


def batch_thread(post_id: str, comments: int = 2) -> tuple[str, dict, list[dict]]:
    url = f"https://www.reddit.com/r/SkincareAddiction/comments/{post_id}/a_title/"
    post = {"post_id": post_id, "url": url, "user_posted": "test_op", "title": f"Which cleanser, {post_id}?",
            "description": "Help me choose.", "num_upvotes": 5, "num_comments": comments,
            "date_posted": "2025-03-01T09:00:00.000Z", "community_name": "SkincareAddiction"}
    records = [comment_record(f"c{post_id}{i}", text=f"Comment {i} on {post_id}.", post_id=post_id, post_url=url,
                              url=f"https://www.reddit.com/r/SkincareAddiction/comments/{post_id}/comment/c{post_id}{i}/")
               for i in range(comments)]
    return url, post, records


class BatchService:
    """A fake Bright Data that answers a job about several threads with each one's records, found by the post id in
    each input link. `dropped` threads are left out of answers about more than one thread (as if Bright Data skipped
    them), but answered when asked about alone."""

    def __init__(self, threads: dict[str, tuple[dict, list[dict]]], dropped: set[str] = frozenset()):
        self.threads = threads
        self.dropped = set(dropped)
        self.jobs: dict[str, tuple[str, list[str]]] = {}

    def __call__(self, method, url, headers, data=None):
        path = urlparse(url).path
        if path.endswith("/trigger"):
            dataset = parse_qs(urlparse(url).query)["dataset_id"][0]
            ids = [parse_thread_url(item["url"])[1] for item in json.loads(data)]
            snapshot_id = f"s{len(self.jobs) + 1}"
            self.jobs[snapshot_id] = (dataset, ids)
            return 200, json.dumps({"snapshot_id": snapshot_id}).encode()
        snapshot_id = path.rstrip("/").rsplit("/", 1)[1]
        dataset, ids = self.jobs[snapshot_id]
        if "/progress/" in path:
            return 200, json.dumps({"status": "ready"}).encode()
        records = []
        for post_id in ids:
            if len(ids) > 1 and post_id in self.dropped:
                continue
            post, comments = self.threads[post_id]
            records += [post] if dataset == POSTS else comments
        return 200, json.dumps(records).encode()

    def triggered(self) -> list[tuple[str, list[str]]]:
        return list(self.jobs.values())


def batch_of(*post_ids, dropped=()):
    made = {post_id: batch_thread(post_id) for post_id in post_ids}
    service = BatchService({pid: (post, comments) for pid, (_, post, comments) in made.items()}, set(dropped))
    return [made[pid][0] for pid in post_ids], service


def test_prefetch_reads_several_threads_in_one_job_per_dataset(tmp_path):
    links, service = batch_of("1bat001", "1bat002", "1bat003")
    client = make_client(tmp_path, service)
    assert client.prefetch([(link, 2) for link in links]) == 3
    assert service.triggered() == [(POSTS, ["1bat001", "1bat002", "1bat003"]), (COMMENTS, ["1bat001", "1bat002", "1bat003"])]
    threads = [client.get_thread(link) for link in links]
    assert len(service.triggered()) == 2  # every read came from the cache
    assert [t.title for t in threads] == ["Which cleanser, 1bat001?", "Which cleanser, 1bat002?", "Which cleanser, 1bat003?"]
    assert [c.id for c in threads[1].comments] == ["c1bat0020", "c1bat0021"]
    assert client.records_used_this_month() == 3 + 6  # 1 per post, 1 per comment


def test_prefetch_leaves_out_threads_already_in_the_cache(tmp_path):
    links, service = batch_of("1bat001", "1bat002", "1bat003")
    client = make_client(tmp_path, service)
    client.get_thread(links[0])
    assert client.prefetch([(link, 2) for link in links]) == 2
    assert service.triggered()[-2:] == [(POSTS, ["1bat002", "1bat003"]), (COMMENTS, ["1bat002", "1bat003"])]


def test_prefetch_goes_in_batches(tmp_path):
    links, service = batch_of("1bat001", "1bat002", "1bat003")
    make_client(tmp_path, service).prefetch([(link, 2) for link in links], batch=2)
    assert [ids for _, ids in service.triggered()] == [["1bat001", "1bat002"], ["1bat001", "1bat002"], ["1bat003"],
                                                       ["1bat003"]]


def test_prefetch_refuses_a_batch_that_could_go_past_the_month(tmp_path):
    links, service = batch_of("1bat001")
    client = make_client(tmp_path, service)
    write_usage(client, BRIGHT_DATA_MONTHLY_RECORDS - 5)
    with pytest.raises(BrightDataError):
        client.prefetch([(links[0], 10)])
    assert service.triggered() == []


def test_a_thread_left_out_of_a_batch_answer_is_read_on_its_own_later(tmp_path):
    links, service = batch_of("1bat001", "1bat002", dropped={"1bat002"})
    client = make_client(tmp_path, service)
    client.prefetch([(link, 2) for link in links])
    assert client.has_thread(links[0]) and not client.has_thread(links[1])
    thread = client.get_thread(links[1])
    assert thread.title == "Which cleanser, 1bat002?" and service.triggered()[-2:] == [(POSTS, ["1bat002"]),
                                                                                      (COMMENTS, ["1bat002"])]
