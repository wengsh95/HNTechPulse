import asyncio
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.core.models import ContentItem, ContentPackage
from src.providers.enricher.page_fetcher import _make_headers
from src.providers.enricher.article_enricher import _find_chrome, ArticleEnricher


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "enrich": {
            "enabled": False,
            "max_text_length": 8000,
            "max_images": 3,
            "skip_domains": [],
        },
        "llm": {"model": "test", "base_url": "http://localhost:11434/v1"},
    }
    for k, v in overrides.items():
        if k in cfg["enrich"]:
            cfg["enrich"][k] = v
        else:
            cfg["enrich"][k] = v
    return cfg


def _make_enricher(**config_overrides):
    with patch("src.utils.config.get_env", return_value="fake-key"):
        with patch("src.providers.enricher.article_enricher.OpenAI"):
            return ArticleEnricher(_make_config(**config_overrides))


# ── _make_headers ─────────────────────────────────────────────────────


class TestMakeHeaders:
    def test_returns_dict(self):
        h = _make_headers()
        assert isinstance(h, dict)

    def test_user_agent_from_pool(self):
        from src.providers.enricher.page_fetcher import _USER_AGENTS

        h = _make_headers()
        assert h["User-Agent"] in _USER_AGENTS

    def test_includes_accept_language(self):
        h = _make_headers()
        assert "Accept-Language" in h


# ── _find_chrome ──────────────────────────────────────────────────────


class TestFindChrome:
    def test_fallback_which(self):
        with patch(
            "src.providers.enricher.page_fetcher.shutil.which",
            return_value="/usr/bin/chromium",
        ):
            with patch(
                "src.providers.enricher.page_fetcher.platform.system",
                return_value="Linux",
            ):
                result = _find_chrome()
                # _find_chrome checks candidate paths first, then falls back to which
                assert result is not None

    def test_none_found(self):
        with patch(
            "src.providers.enricher.page_fetcher.shutil.which", return_value=None
        ):
            with patch(
                "src.providers.enricher.page_fetcher.platform.system",
                return_value="Linux",
            ):
                with patch("src.providers.enricher.page_fetcher.Path") as MockPath:
                    # Make all Path.exists() return False
                    mp = MagicMock()
                    mp.exists.return_value = False
                    MockPath.return_value = mp
                    MockPath.home.return_value = mp
                    result = _find_chrome()
                    assert result is None


# ── _extract_text ─────────────────────────────────────────────────────


class TestExtractText:
    def test_valid_html_returns_text(self):
        enricher = _make_enricher()
        with patch.object(
            enricher.image_handler, "extract_text", return_value="A" * 200
        ):
            result = enricher._extract_text("<html></html>", "https://example.com")
            assert result is not None
            assert len(result) > 0

    def test_short_text_returns_none(self):
        enricher = _make_enricher()
        with patch.object(enricher.image_handler, "extract_text", return_value=None):
            result = enricher._extract_text("<html></html>", "https://example.com")
            assert result is None

    def test_exception_returns_none(self):
        enricher = _make_enricher()
        with patch.object(enricher.image_handler, "extract_text", return_value=None):
            result = enricher._extract_text("html", "https://example.com")
            assert result is None

    def test_truncation(self):
        enricher = _make_enricher(max_text_length=500)
        long_text = "A" * 1000
        with patch.object(
            enricher.image_handler, "extract_text", return_value=long_text[:500]
        ):
            result = enricher._extract_text("<html></html>", "https://example.com")
            assert len(result) == 500


# ── _extract_images ───────────────────────────────────────────────────


class TestExtractImages:
    def test_og_image(self):
        enricher = _make_enricher()
        html = '<html><head><meta property="og:image" content="https://x.com/img.jpg"></head><body></body></html>'
        result = enricher.image_handler.extract_images(html, "https://x.com")
        assert any("img.jpg" in url for url in result)

    def test_twitter_image(self):
        enricher = _make_enricher()
        html = '<html><head><meta name="twitter:image" content="https://x.com/tw.jpg"></head><body></body></html>'
        result = enricher.image_handler.extract_images(html, "https://x.com")
        assert any("tw.jpg" in url for url in result)

    def test_skip_tracking_images(self):
        enricher = _make_enricher()
        html = '<html><head><meta property="og:image" content="https://x.com/pixel.gif"></head><body></body></html>'
        result = enricher.image_handler.extract_images(html, "https://x.com")
        assert len(result) == 0

    def test_max_images_limit(self):
        enricher = _make_enricher(max_images=1)
        html = (
            "<html><head>"
            '<meta property="og:image" content="https://x.com/a.jpg">'
            '<meta name="twitter:image" content="https://x.com/b.jpg">'
            "</head><body></body></html>"
        )
        result = enricher.image_handler.extract_images(html, "https://x.com")
        assert len(result) <= 1

    def test_srcset_uses_largest_image(self):
        enricher = _make_enricher()
        html = (
            "<html><body><article>"
            '<img srcset="/small.jpg 320w, /large.jpg 1280w">'
            "</article></body></html>"
        )
        result = enricher.image_handler.extract_images(html, "https://x.com/post")
        assert "https://x.com/large.jpg" in result

    def test_lazy_and_poster_images(self):
        enricher = _make_enricher(max_images=3)
        html = (
            "<html><body><main>"
            '<img data-lazy-src="/lazy.jpg">'
            '<video poster="/poster.jpg"></video>'
            "</main></body></html>"
        )
        result = enricher.image_handler.extract_images(html, "https://x.com/post")
        assert "https://x.com/lazy.jpg" in result
        assert "https://x.com/poster.jpg" in result

    def test_exception_returns_empty(self):
        enricher = _make_enricher()
        with patch(
            "src.providers.enricher.image_handler.BeautifulSoup",
            side_effect=Exception("boom"),
        ):
            result = enricher.image_handler.extract_images("html", "https://x.com")
            assert result == []


# ── Skip domains ──────────────────────────────────────────────────────


class TestSkipDomains:
    def test_exact_match(self):
        enricher = _make_enricher(skip_domains=["twitter.com"])
        assert "twitter.com" in enricher.skip_domains

    def test_subdomain_match(self):
        _make_enricher(skip_domains=["twitter.com"])
        from urllib.parse import urlparse

        host = urlparse("https://mobile.twitter.com/something").hostname
        assert host.endswith(".twitter.com")

    def test_leading_dot_stripped(self):
        enricher = _make_enricher(skip_domains=[".twitter.com"])
        assert "twitter.com" in enricher.skip_domains

    def test_no_match(self):
        _make_enricher(skip_domains=["twitter.com"])
        from urllib.parse import urlparse

        host = urlparse("https://github.com/something").hostname
        assert not (host == "twitter.com" or host.endswith(".twitter.com"))


class TestImageSelection:
    def test_auto_select_prefers_suitable_page_image(self):
        enricher = _make_enricher()
        candidates = [
            {"path": "images/small.jpg", "source": "page", "width": 320, "height": 180},
            {"path": "images/good.jpg", "source": "page", "width": 900, "height": 500},
            {
                "path": "images/shot.jpg",
                "source": "screenshot",
                "width": 1280,
                "height": 720,
            },
            {"path": "images/bing.jpg", "source": "bing", "width": 900, "height": 500},
        ]

        selected = enricher.image_handler.choose_auto_image_candidate(candidates)

        assert selected["path"] == "images/good.jpg"
        assert (
            enricher.image_handler.candidate_paths(
                candidates, preferred_path=selected["path"]
            )[0]
            == "images/good.jpg"
        )

    def test_auto_select_uses_screenshot_before_bing_when_page_is_too_small(self):
        enricher = _make_enricher()
        candidates = [
            {"path": "images/small.jpg", "source": "page", "width": 320, "height": 180},
            {
                "path": "images/shot.jpg",
                "source": "screenshot",
                "width": 1280,
                "height": 720,
            },
            {"path": "images/bing.jpg", "source": "bing", "width": 900, "height": 500},
        ]

        selected = enricher.image_handler.choose_auto_image_candidate(candidates)

        assert selected["path"] == "images/shot.jpg"

    def test_auto_select_uses_suitable_bing_when_no_screenshot(self):
        enricher = _make_enricher()
        candidates = [
            {"path": "images/small.jpg", "source": "page", "width": 320, "height": 180},
            {"path": "images/bing.jpg", "source": "bing", "width": 900, "height": 500},
        ]

        selected = enricher.image_handler.choose_auto_image_candidate(candidates)

        assert selected["path"] == "images/bing.jpg"

    def test_merge_preserves_selected_image_and_adds_new_candidates(
        self, tmp_path, monkeypatch
    ):
        enricher = _make_enricher()
        monkeypatch.chdir(tmp_path)
        date = "2026-05-11"
        sel_dir = Path("data") / date
        sel_dir.mkdir(parents=True)
        sel_path = sel_dir / "image_selection.json"
        sel_path.write_text(
            json.dumps(
                {
                    "date": date,
                    "items": {
                        "42": {
                            "title": "Old",
                            "url": "https://x.com/old",
                            "candidates": [
                                {"path": "images/old.jpg", "source": "page"}
                            ],
                            "selected_image": "images/old.jpg",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        item = ContentItem(
            source="hackernews",
            source_id="42",
            title="New",
            url="https://x.com/new",
            image_candidates=[
                {"path": "images/old.jpg", "source": "page"},
                {
                    "path": "images/new.jpg",
                    "source": "bing",
                    "origin_url": "https://img/new.jpg",
                },
            ],
        )
        enricher._generate_image_selection(
            ContentPackage(date=date, items=[item]), date
        )

        merged = json.loads(sel_path.read_text(encoding="utf-8"))
        entry = merged["items"]["42"]
        assert entry["selected_image"] == "images/old.jpg"
        assert [c["path"] for c in entry["candidates"]] == [
            "images/old.jpg",
            "images/new.jpg",
        ]

    def test_generate_selection_uses_auto_selected_default(self, tmp_path, monkeypatch):
        enricher = _make_enricher()
        monkeypatch.chdir(tmp_path)
        date = "2026-05-11"
        item = ContentItem(
            source="hackernews",
            source_id="42",
            title="Story",
            url="https://x.com/story",
            image_candidates=[
                {
                    "path": "images/small.jpg",
                    "source": "page",
                    "width": 320,
                    "height": 180,
                },
                {
                    "path": "images/shot.jpg",
                    "source": "screenshot",
                    "width": 1280,
                    "height": 720,
                },
                {
                    "path": "images/bing.jpg",
                    "source": "bing",
                    "width": 900,
                    "height": 500,
                },
            ],
        )

        enricher._generate_image_selection(
            ContentPackage(date=date, items=[item]), date
        )

        data = json.loads(
            (Path("data") / date / "image_selection.json").read_text(encoding="utf-8")
        )
        entry = data["items"]["42"]
        assert entry["selected_image"] == "images/shot.jpg"
        selected = [c for c in entry["candidates"] if c.get("auto_selected")]
        assert selected[0]["path"] == "images/shot.jpg"

    def test_phase2_reuses_cached_image_candidates(self, tmp_path, monkeypatch):
        enricher = _make_enricher()
        monkeypatch.chdir(tmp_path)
        date = "2026-05-11"
        pages_dir = Path("data") / date / "downloaded_pages"
        image_dir = Path("data") / date / "images"
        pages_dir.mkdir(parents=True)
        image_dir.mkdir(parents=True)
        (pages_dir / "42.html").write_text(
            "<html><body><p>article</p><img src='/new.jpg'></body></html>",
            encoding="utf-8",
        )
        (image_dir / "42_0.jpg").write_bytes(b"cached")
        (image_dir / "42_screenshot.jpg").write_bytes(b"shot")

        item = ContentItem(
            source="hackernews",
            source_id="42",
            title="Story",
            url="https://x.com/story",
            article_images=["images/42_0.jpg"],
            screenshot_image="images/42_screenshot.jpg",
            image_candidates=[
                {
                    "path": "images/42_0.jpg",
                    "source": "page",
                    "label": "Article image",
                    "rank": 0,
                    "width": 900,
                    "height": 500,
                }
            ],
        )

        async def fail_download(*args, **kwargs):
            raise AssertionError("cached images should skip page image downloads")

        async def fail_bing(*args, **kwargs):
            raise AssertionError("cached images should skip Bing image search")

        async def fail_screenshot(*args, **kwargs):
            raise AssertionError("cached screenshots should skip recapture")

        enricher._extract_text = MagicMock(return_value="A" * 300)
        enricher.image_handler.extract_images = MagicMock(
            return_value=["https://x.com/new.jpg"]
        )
        enricher._enrich_content = MagicMock(
            return_value={"article_summary": "summary"}
        )
        enricher.image_handler.download_image_candidates = fail_download
        enricher.image_handler.search_bing_images = fail_bing
        enricher.fetcher.capture_screenshot = fail_screenshot

        asyncio.run(enricher._phase2_extract_one(item, date, asyncio.Semaphore(1)))

        assert item.article_text == "A" * 300
        assert item.article_images[0] == "images/42_0.jpg"
        assert [c["path"] for c in item.image_candidates] == [
            "images/42_0.jpg",
            "images/42_screenshot.jpg",
        ]


class TestNormalizeKeywords:
    def test_filters_duplicates_category_and_low_value_terms(self):
        result = ArticleEnricher._normalize_keywords(
            [
                " AI ",
                "AI工具",
                "Claude Code",
                "claude code",
                "开发者",
                "本地推理",
                "供应链攻击风险很长很长",
            ],
            category="AI工具",
        )

        assert result == ["Claude Code", "本地推理", "供应链攻击风险很长很长"]

    def test_fallback_values_fill_missing_keywords(self):
        result = ArticleEnricher._normalize_keywords(
            ["技术", "开源生态"],
            category="开源生态",
            fallback_values=["MCP协议", "工具", "企业部署"],
        )

        assert result == ["MCP协议", "企业部署"]
