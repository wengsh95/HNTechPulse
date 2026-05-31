from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from src.providers.fetcher.hn_fetcher import HNFetcher
from src.providers.fetcher.models import HNStory, HNComment


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "hn": {
            "base_url": "https://hacker-news.firebaseio.com/v0",
            "top_stories_count": 100,
            "target_stories_count": 10,
            "request_timeout": (5, 15),
        },
    }
    for k, v in overrides.items():
        cfg["hn"][k] = v
    return cfg


def _make_story(
    story_id=1,
    title="Test",
    score=100,
    descendants=50,
    ts=1700000000,
    url="https://example.com",
):
    return HNStory(
        id=story_id,
        title=title,
        url=url,
        score=score,
        descendants=descendants,
        time=ts,
        text=None,
        by="user",
    )


def _make_comment(cid=1, author="user", text="comment text", ts=1700000000):
    return HNComment(id=cid, author=author, text=text, time=ts)


def _make_fetcher(**config_overrides):
    with patch("src.providers.fetcher.hn_fetcher.requests.Session"):
        return HNFetcher(_make_config(**config_overrides))


# ── Timeout parsing ───────────────────────────────────────────────────


class TestTimeoutParsing:
    def test_list_timeout(self):
        fetcher = _make_fetcher(request_timeout=[3, 10])
        assert fetcher.request_timeout == (3, 10)

    def test_tuple_timeout(self):
        fetcher = _make_fetcher(request_timeout=(5, 15))
        assert fetcher.request_timeout == (5, 15)

    def test_default_timeout(self):
        fetcher = _make_fetcher()
        assert fetcher.request_timeout == (5, 15)


# ── _filter_stories_by_time ───────────────────────────────────────────


class TestFilterStoriesByTime:
    def test_stories_within_range(self):
        fetcher = _make_fetcher()
        # 2024-01-14 in Beijing is 2024-01-14 00:00:00+08:00 to 23:59:59+08:00
        # Unix timestamp for 2024-01-14 00:00:00 CST = 1705161600
        ts = 1705161600 + 43200  # noon Beijing time
        stories = [_make_story(ts=ts)]
        result = fetcher._filter_stories_by_time(stories, "2024-01-15")
        assert len(result) == 1

    def test_stories_outside_range(self):
        fetcher = _make_fetcher()
        ts = 1705161600 - 86400  # two days before
        stories = [_make_story(ts=ts)]
        result = fetcher._filter_stories_by_time(stories, "2024-01-15")
        assert len(result) == 0

    def test_boundary_start(self):
        fetcher = _make_fetcher()
        # Exact start boundary: yesterday 06:00 Beijing
        target_date = datetime.strptime("2024-01-15", "%Y-%m-%d")
        yesterday = target_date - timedelta(days=1)
        beijing_tz = timezone(timedelta(hours=8))
        start = datetime(
            yesterday.year, yesterday.month, yesterday.day, 6, 0, 0, tzinfo=beijing_tz
        )
        ts = int(start.timestamp())
        stories = [_make_story(ts=ts)]
        result = fetcher._filter_stories_by_time(stories, "2024-01-15")
        assert len(result) == 1

    def test_boundary_end(self):
        fetcher = _make_fetcher()
        target_date = datetime.strptime("2024-01-15", "%Y-%m-%d")
        yesterday = target_date - timedelta(days=1)
        beijing_tz = timezone(timedelta(hours=8))
        end = datetime(
            yesterday.year,
            yesterday.month,
            yesterday.day,
            23,
            59,
            59,
            tzinfo=beijing_tz,
        )
        ts = int(end.timestamp())
        stories = [_make_story(ts=ts)]
        result = fetcher._filter_stories_by_time(stories, "2024-01-15")
        assert len(result) == 1


# ── _select_top_stories ──────────────────────────────────────────────


class TestSelectTopStories:
    def test_sorted_by_score_and_descendants(self):
        fetcher = _make_fetcher()
        s1 = _make_story(story_id=1, score=200, descendants=10)
        s2 = _make_story(story_id=2, score=200, descendants=50)
        s3 = _make_story(story_id=3, score=100, descendants=100)
        result = fetcher._select_top_stories([s3, s1, s2])
        assert result[0].id == 2
        assert result[1].id == 1
        assert result[2].id == 3

    def test_limited_count(self):
        fetcher = _make_fetcher(target_stories_count=2)
        stories = [_make_story(story_id=i, score=i * 10) for i in range(5)]
        result = fetcher._select_top_stories(stories)
        assert len(result) == 2

    def test_fewer_than_target(self):
        fetcher = _make_fetcher(target_stories_count=10)
        stories = [_make_story(story_id=1, score=100)]
        result = fetcher._select_top_stories(stories)
        assert len(result) == 1


# ── _to_content_package ──────────────────────────────────────────────


class TestToContentPackage:
    def test_basic_conversion(self):
        fetcher = _make_fetcher()
        stories = [
            _make_story(story_id=42, title="Hello HN", score=500, descendants=30)
        ]
        comments = {42: [_make_comment(cid=1, author="alice", text="nice")]}
        pkg = fetcher._to_content_package(stories, comments, "2024-01-15")
        assert pkg.date == "2024-01-15"
        assert len(pkg.items) >= 1
        item = pkg.items[0]
        assert item.source == "hackernews"
        assert item.source_id == "42"
        assert item.title == "Hello HN"
        assert item.score == 500
        assert item.comment_count == 30
        assert len(item.comments) == 1
        assert item.comments[0].author == "alice"

    def test_no_truncation(self):
        """_to_content_package no longer truncates; all stories are kept."""
        fetcher = _make_fetcher()
        stories = [_make_story(story_id=i) for i in range(20)]
        pkg = fetcher._to_content_package(stories, {}, "2024-01-15")
        assert len(pkg.items) == 20

    def test_empty_comments(self):
        """Stories without comments in dict get empty comment list."""
        fetcher = _make_fetcher()
        stories = [_make_story(story_id=1), _make_story(story_id=2)]
        pkg = fetcher._to_content_package(stories, {}, "2024-01-15")
        assert len(pkg.items) == 2
        assert len(pkg.items[0].comments) == 0
        assert len(pkg.items[1].comments) == 0


# ── _story_to_dict / _dict_to_story ──────────────────────────────────


class TestStoryDictRoundTrip:
    def test_round_trip(self):
        fetcher = _make_fetcher()
        story = _make_story(
            story_id=99,
            title="Round",
            score=42,
            descendants=7,
            ts=1700000000,
            url="https://x.com",
        )
        d = fetcher._story_to_dict(story)
        restored = fetcher._dict_to_story(d)
        assert restored.id == 99
        assert restored.title == "Round"
        assert restored.score == 42
        assert restored.descendants == 7
        assert restored.url == "https://x.com"


# ── _comment_to_dict / _dict_to_comment ──────────────────────────────


class TestCommentDictRoundTrip:
    def test_round_trip(self):
        fetcher = _make_fetcher()
        comment = _make_comment(cid=10, author="bob", text="hello", ts=1700000000)
        d = fetcher._comment_to_dict(comment)
        restored = fetcher._dict_to_comment(d)
        assert restored.id == 10
        assert restored.author == "bob"
        assert restored.text == "hello"
        assert restored.time == 1700000000
