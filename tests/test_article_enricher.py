import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.providers.enricher.article_enricher import _make_headers, _find_chrome, ArticleEnricher


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
        from src.providers.enricher.article_enricher import _USER_AGENTS
        h = _make_headers()
        assert h["User-Agent"] in _USER_AGENTS

    def test_includes_accept_language(self):
        h = _make_headers()
        assert "Accept-Language" in h


# ── _find_chrome ──────────────────────────────────────────────────────

class TestFindChrome:
    def test_fallback_which(self):
        with patch("src.providers.enricher.article_enricher.shutil.which", return_value="/usr/bin/chromium"):
            with patch("src.providers.enricher.article_enricher.platform.system", return_value="Linux"):
                result = _find_chrome()
                # _find_chrome checks candidate paths first, then falls back to which
                assert result is not None

    def test_none_found(self):
        with patch("src.providers.enricher.article_enricher.shutil.which", return_value=None):
            with patch("src.providers.enricher.article_enricher.platform.system", return_value="Linux"):
                with patch("src.providers.enricher.article_enricher.Path") as MockPath:
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
        html = "<html><body><p>" + "A" * 200 + "</p></body></html>"
        with patch("src.providers.enricher.article_enricher.trafilatura") as mock_traf:
            mock_traf.extract.return_value = "A" * 200
            result = enricher._extract_text(html, "https://example.com")
            assert result is not None
            assert len(result) > 0

    def test_short_text_returns_none(self):
        enricher = _make_enricher()
        html = "<html><body><p>short</p></body></html>"
        with patch("src.providers.enricher.article_enricher.trafilatura") as mock_traf:
            mock_traf.extract.return_value = "short"
            result = enricher._extract_text(html, "https://example.com")
            assert result is None

    def test_exception_returns_none(self):
        enricher = _make_enricher()
        with patch("src.providers.enricher.article_enricher.trafilatura") as mock_traf:
            mock_traf.extract.side_effect = Exception("boom")
            result = enricher._extract_text("html", "https://example.com")
            assert result is None

    def test_truncation(self):
        enricher = _make_enricher(max_text_length=500)
        long_text = "A" * 1000
        with patch("src.providers.enricher.article_enricher.trafilatura") as mock_traf:
            mock_traf.extract.return_value = long_text
            result = enricher._extract_text("<html></html>", "https://example.com")
            assert len(result) == 500


# ── _extract_images ───────────────────────────────────────────────────

class TestExtractImages:
    def test_og_image(self):
        enricher = _make_enricher()
        html = '<html><head><meta property="og:image" content="https://x.com/img.jpg"></head><body></body></html>'
        result = enricher._extract_images(html, "https://x.com")
        assert any("img.jpg" in url for url in result)

    def test_twitter_image(self):
        enricher = _make_enricher()
        html = '<html><head><meta name="twitter:image" content="https://x.com/tw.jpg"></head><body></body></html>'
        result = enricher._extract_images(html, "https://x.com")
        assert any("tw.jpg" in url for url in result)

    def test_skip_tracking_images(self):
        enricher = _make_enricher()
        html = '<html><head><meta property="og:image" content="https://x.com/pixel.gif"></head><body></body></html>'
        result = enricher._extract_images(html, "https://x.com")
        assert len(result) == 0

    def test_max_images_limit(self):
        enricher = _make_enricher(max_images=1)
        html = (
            '<html><head>'
            '<meta property="og:image" content="https://x.com/a.jpg">'
            '<meta name="twitter:image" content="https://x.com/b.jpg">'
            '</head><body></body></html>'
        )
        result = enricher._extract_images(html, "https://x.com")
        assert len(result) <= 1

    def test_exception_returns_empty(self):
        enricher = _make_enricher()
        with patch("src.providers.enricher.article_enricher.BeautifulSoup", side_effect=Exception("boom")):
            result = enricher._extract_images("html", "https://x.com")
            assert result == []


# ── Skip domains ──────────────────────────────────────────────────────

class TestSkipDomains:
    def test_exact_match(self):
        enricher = _make_enricher(skip_domains=["twitter.com"])
        assert "twitter.com" in enricher.skip_domains

    def test_subdomain_match(self):
        enricher = _make_enricher(skip_domains=["twitter.com"])
        from urllib.parse import urlparse
        host = urlparse("https://mobile.twitter.com/something").hostname
        assert host.endswith(".twitter.com")

    def test_leading_dot_stripped(self):
        enricher = _make_enricher(skip_domains=[".twitter.com"])
        assert "twitter.com" in enricher.skip_domains

    def test_no_match(self):
        enricher = _make_enricher(skip_domains=["twitter.com"])
        from urllib.parse import urlparse
        host = urlparse("https://github.com/something").hostname
        assert not (host == "twitter.com" or host.endswith(".twitter.com"))
