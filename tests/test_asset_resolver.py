"""Tests for the single image-asset resolution/staging seam."""

from pathlib import Path
from types import SimpleNamespace

from src.pipeline.asset_resolver import (
    content_item_for_story,
    is_remote,
    relative_image_path,
    resolve_existing_local,
    resolve_local_path,
    stage_content_images,
)
from src.pipeline.paths import media_images_dir, date_root


def _item(title="Story 0", images=None):
    return SimpleNamespace(
        source_id="123",
        title=title,
        url="https://example.com/0",
        article_images=images or [],
        logo_image=None,
        screenshot_image=None,
        image_candidates=[],
    )


class TestIsRemote:
    def test_http_is_remote(self):
        assert is_remote("https://example.com/img.png")
        assert is_remote("http://x.com/1")

    def test_local_paths_are_not_remote(self):
        assert not is_remote("images/foo.jpg")
        assert not is_remote("data/x/y.png")
        assert not is_remote(None)
        assert not is_remote("")


class TestResolveLocalPath:
    def test_absolute_passthrough(self):
        assert resolve_local_path("2026-08-18", "C:/x/foo.png") == Path("C:/x/foo.png")

    def test_images_prefix_resolves_to_media_images_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = resolve_local_path("2026-08-18", "images/foo.jpg")
        assert p == media_images_dir("2026-08-18") / "foo.jpg"

    def test_relative_resolves_to_date_root_with_media_fallback(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        # Non-existent relative path → date_root, no media fallback.
        p = resolve_local_path("2026-08-18", "pipeline/x/y.png")
        assert p == date_root("2026-08-18") / "pipeline/x/y.png"

        # When the media fallback exists, it wins.
        media = date_root("2026-08-18") / "media" / "x" / "y.png"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"x")
        p2 = resolve_local_path("2026-08-18", "x/y.png")
        assert p2 == media


class TestResolveExistingLocal:
    def test_remote_returns_none(self):
        assert resolve_existing_local("2026-08-18", "https://x/y.png") is None

    def test_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert resolve_existing_local("2026-08-18", "images/nope.jpg") is None

    def test_existing_returns_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        f = media_images_dir("2026-08-18") / "ok.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
        assert resolve_existing_local("2026-08-18", "images/ok.jpg") == f


class TestRelativeImagePath:
    def test_images_prefix_preserved(self):
        assert relative_image_path("images/a/b.jpg") == "images/a/b.jpg"

    def test_bare_name_wrapped(self):
        assert relative_image_path("foo.jpg") == "images/foo.jpg"

    def test_subdir_wrapped_to_basename(self):
        assert relative_image_path("pipeline/x/foo.jpg") == "images/foo.jpg"


class TestContentItemForStory:
    def _content(self):
        return SimpleNamespace(
            items=[_item("Story 0"), _item("Story 1", images=["images/b.jpg"])]
        )

    def test_index_hit_with_matching_title(self):
        c = self._content()
        assert (
            content_item_for_story(c, {"story_index": 0, "source_title": "Story 0"})
            is c.items[0]
        )

    def test_index_miss_falls_back_to_title(self):
        c = self._content()
        assert (
            content_item_for_story(c, {"story_index": 5, "source_title": "Story 1"})
            is c.items[1]
        )

    def test_index_hit_but_title_mismatch_uses_title(self):
        c = self._content()
        # index 0 but the props title names Story 1: title wins.
        assert (
            content_item_for_story(c, {"story_index": 0, "source_title": "Story 1"})
            is c.items[1]
        )

    def test_no_title_and_index_in_range_uses_index(self):
        c = self._content()
        assert content_item_for_story(c, {"story_index": 0}) is c.items[0]

    def test_empty_content_returns_none(self):
        assert (
            content_item_for_story(SimpleNamespace(items=[]), {"story_index": 0})
            is None
        )
        assert content_item_for_story(None, {}) is None


class TestStageContentImages:
    def test_copies_article_logo_screenshot_and_selected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-08-18"
        img_dir = media_images_dir(date)
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "a.jpg").write_bytes(b"a")
        (img_dir / "logo.png").write_bytes(b"l")
        (img_dir / "shot.png").write_bytes(b"s")
        (img_dir / "sel.jpg").write_bytes(b"x")
        # selected story image
        from src.utils.atomic_io import atomic_write_json
        from src.pipeline.paths import pipeline_path

        atomic_write_json(
            pipeline_path(date, "story_images.json"),
            {"stories": [{"selected_image": "images/sel.jpg"}]},
        )
        content = SimpleNamespace(
            items=[
                _item(
                    images=["images/a.jpg"],
                )
            ]
        )
        content.items[0].logo_image = "images/logo.png"
        content.items[0].screenshot_image = "images/shot.png"

        target = date_root(date) / "public" / "images"
        copied = stage_content_images(content, date, target)

        assert copied == 4
        assert sorted(p.name for p in target.iterdir()) == [
            "a.jpg",
            "logo.png",
            "sel.jpg",
            "shot.png",
        ]

    def test_idempotent_no_double_copy(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-08-18"
        img_dir = media_images_dir(date)
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "a.jpg").write_bytes(b"a")
        content = SimpleNamespace(items=[_item(images=["images/a.jpg"])])
        target = date_root(date) / "public" / "images"
        first = stage_content_images(content, date, target)
        second = stage_content_images(content, date, target)
        assert first == 1
        assert second == 0

    def test_candidates_respect_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-08-18"
        img_dir = media_images_dir(date)
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "cand.jpg").write_bytes(b"c")
        (img_dir / "art.jpg").write_bytes(b"a")
        item = _item(images=["images/art.jpg"])
        item.image_candidates = [{"path": "images/cand.jpg"}]
        content = SimpleNamespace(items=[item])
        target = date_root(date) / "public" / "images"

        with_candidates = stage_content_images(content, date, target)
        assert with_candidates == 2

        target2 = date_root(date) / "public2" / "images"
        without = stage_content_images(content, date, target2, include_candidates=False)
        assert without == 1

    def test_remote_and_missing_skipped(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-08-18"
        item = _item(images=["https://x/y.jpg", "images/missing.jpg"])
        content = SimpleNamespace(items=[item])
        target = date_root(date) / "public" / "images"
        assert stage_content_images(content, date, target) == 0
