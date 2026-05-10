import asyncio
import io
import json
import logging
import platform
import random
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from PIL import Image
from openai import OpenAI
import trafilatura
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.core.models import ContentPackage
from src.core.prompts import render_prompt

# Rotating User-Agent pool — real Chrome/Firefox on Windows/macOS
_USER_AGENTS = [
    # Chrome 131 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome 131 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Edge 131 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Firefox 133 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Chrome 130 on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Base browser headers (User-Agent replaced per request)
_BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Chrome launch args: anti-detection + console/network logging
_CHROME_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--enable-features=NetworkService,NetworkServiceInProcess",
    "--enable-logging",
    "--v=1",
]

def _make_headers() -> Dict[str, str]:
    """Return a copy of base headers with a randomly chosen User-Agent."""
    headers = dict(_BASE_HEADERS)
    headers["User-Agent"] = random.choice(_USER_AGENTS)
    return headers


def _find_chrome() -> Optional[str]:
    """Auto-detect a local Chrome/Chromium executable."""
    system = platform.system()
    candidates = []

    if system == "Windows":
        candidates = [
            # Chrome stable
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            # Chrome — user install
            str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
            # Chromium
            str(Path.home() / r"AppData\Local\Chromium\Application\chrome.exe"),
            # Edge (Chromium-based, Playwright-compatible)
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/microsoft-edge",
            "/snap/bin/chromium",
        ]

    for path in candidates:
        if path and shutil.which(path) if system != "Windows" else Path(path).exists():
            return path

    # Fallback: search PATH
    for name in ["google-chrome", "chromium-browser", "chromium", "chrome", "msedge"]:
        found = shutil.which(name)
        if found:
            return found

    return None


class ArticleEnricher:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        enrich_cfg = config.get("enrich", {})
        # Child of the main "hn_techpulse" logger — inherits its file handler
        # via propagation, so enricher-level failures land in logs/app_*.log.
        self.logger = logging.getLogger("hn_techpulse.enricher")

        self.enabled = enrich_cfg.get("enabled", False)
        self.max_text_length = enrich_cfg.get("max_text_length", 8000)
        self.max_images = enrich_cfg.get("max_images", 3)
        self.max_image_size = enrich_cfg.get("max_image_size", 5 * 1024 * 1024)
        self.request_timeout = enrich_cfg.get("request_timeout", 15)
        self.max_concurrent = enrich_cfg.get("max_concurrent", 5)
        self.summary_max_tokens = enrich_cfg.get("summary_max_tokens", 512)
        self.retry_count = enrich_cfg.get("retry_count", 3)
        self.request_delay = enrich_cfg.get("request_delay", 0.5)
        self.use_headless = enrich_cfg.get("headless", True)
        self.use_headed = enrich_cfg.get("headed", True)
        self.bing_image_search = enrich_cfg.get("bing_image_search", True)
        self.bing_max_results = enrich_cfg.get("bing_max_results", 3)
        self.screenshot_enabled = enrich_cfg.get("screenshot_enabled", True)
        self.save_fetched_html = enrich_cfg.get("save_fetched_html", True)
        self.headless_batch = enrich_cfg.get("headless_batch", True)
        self.browser_executable = enrich_cfg.get("browser_executable") or _find_chrome()
        if self.browser_executable:
            self.logger.debug(f"Using browser: {self.browser_executable}")

        # Domains to skip outright — heavy anti-bot, login walls, or
        # sites known to serve nothing useful to scrapers.
        self.skip_domains = {
            d.lower().lstrip(".")
            for d in enrich_cfg.get("skip_domains", []) or []
        }

        _target = enrich_cfg.get("image_target_size", [1280, 720])
        self.image_target_width = _target[0]
        self.image_target_height = _target[1]

        # Independent LLM config for summarization
        llm_cfg = enrich_cfg.get("llm", {})
        llm_base_url = llm_cfg.get("base_url", config.get("llm", {}).get("base_url", ""))
        llm_model = llm_cfg.get("model", config.get("llm", {}).get("model", ""))
        llm_max_tokens = llm_cfg.get("max_tokens", self.summary_max_tokens)
        llm_temperature = llm_cfg.get("temperature", 0.5)

        from src.utils.config import get_env
        api_key = get_env("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        self.llm_client = OpenAI(
            api_key=api_key,
            base_url=llm_base_url,
        )
        self.llm_model = llm_model
        self.llm_max_tokens = llm_max_tokens
        self.llm_temperature = llm_temperature

        # Load summarize prompt
        self._summarize_prompt = self._load_prompt("prompts/article_summarize.md")

    @staticmethod
    def _load_prompt(path: str) -> str:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    def _pages_dir(self, date: str) -> Path:
        return Path(f"data/{date}/downloaded_pages")

    def enrich(self, content: ContentPackage, date: str) -> ContentPackage:
        if not self.enabled:
            self.logger.info("Article enrichment disabled, skipping")
            return content

        self.logger.info(f"Enriching {len(content.items)} items...")

        # Load image selections (user-chosen images from previous runs)
        self._load_image_selection(content, date)

        # Load checkpoint (enrichment.json)
        cache_path = Path(f"data/{date}/enrichment.json")
        if cache_path.exists():
            self._load_from_cache(content, cache_path)

        # Ensure downloaded_pages directory exists
        pages_dir = self._pages_dir(date)
        pages_dir.mkdir(parents=True, exist_ok=True)

        # Classify items
        classified = self._classify_items(content, date)
        done = len(classified["done"]) + len(classified["skipped"])
        to_fetch = len(classified["full"])
        to_extract = len(classified["phase2_only"])
        self.logger.info(
            f"Classified: {done} done/skipped, {to_fetch} need fetch, "
            f"{to_extract} have HTML (phase2 only)"
        )

        if not classified["full"] and not classified["phase2_only"]:
            self._generate_image_selection(content, date)
            self._save_to_cache(content, cache_path)
            self.logger.info("All items already enriched, skipping")
            return content

        # Run async enrichment
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._enrich_items(content, date, classified))
                future.result()
        except RuntimeError:
            asyncio.run(self._enrich_items(content, date, classified))

        # Generate image selection file for user review
        self._generate_image_selection(content, date)

        # Save checkpoint
        self._save_to_cache(content, cache_path)
        self.logger.info("Enrichment complete")
        return content

    async def _enrich_items(self, content: ContentPackage, date: str, classified: dict):
        # Phase 1: Fetch HTML for 'full' items
        if classified["full"]:
            await self._phase1_fetch_all(content, date, classified["full"])

        # Determine which items need Phase 2 extraction
        # (Phase 1 successes + pre-existing phase2_only items)
        phase2_items = list(classified["phase2_only"])
        for item in classified["full"]:
            if item.enrichment_source not in ("fetch_failed", "skipped", "error"):
                phase2_items.append(item)

        # Phase 2: Extract from on-disk HTML
        if phase2_items:
            await self._phase2_extract_all(phase2_items, date)

    # ── Item Classification ────────────────────────────────────

    def _classify_items(self, content: ContentPackage, date: str) -> dict:
        """Classify items into done/phase2_only/full/skipped buckets.

        Returns:
            dict with keys 'done', 'phase2_only', 'full', 'skipped' —
            each maps to a list of ContentItem.
        """
        pages_dir = self._pages_dir(date)
        result = {"done": [], "phase2_only": [], "full": [], "skipped": []}

        for item in content.items:
            # Already enriched (from cache or previous run)
            if item.article_text is not None or item.article_summary is not None:
                result["done"].append(item)
                continue

            # No URL to fetch
            if not item.url:
                item.enrichment_source = "skipped"
                result["skipped"].append(item)
                continue

            # Domain skip list
            if self.skip_domains:
                host = (urlparse(item.url).hostname or "").lower().lstrip(".")
                if any(host == d or host.endswith("." + d) for d in self.skip_domains):
                    item.enrichment_source = "skipped"
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.screenshot_image = None
                    result["skipped"].append(item)
                    continue

            # HTML file exists on disk → validate it has extractable content
            html_path = pages_dir / f"{item.source_id}.html"
            if html_path.exists():
                try:
                    html = html_path.read_text(encoding="utf-8", errors="replace")
                    if self._extract_text(html, item.url or ""):
                        result["phase2_only"].append(item)
                    else:
                        self.logger.info(
                            f"[stale_html] {item.title[:50]} — "
                            f"cached HTML has no extractable content, will re-fetch"
                        )
                        result["full"].append(item)
                except Exception:
                    result["full"].append(item)
            else:
                result["full"].append(item)

        return result

    # ── Phase 1: Fetch HTML to disk ────────────────────────────

    async def _phase1_fetch_all(self, content: ContentPackage, date: str, items: list):
        """Fetch HTML for 'full' items using aiohttp → headless → headed fallback."""
        pages_dir = self._pages_dir(date)
        remaining = items
        total = len(items)

        # Strategy 1: aiohttp (fast, non-blocking)
        aiohttp_failed = []
        for item in remaining:
            strategy = await self._phase1_fetch_one_aiohttp(item, pages_dir)
            if strategy:
                item.enrichment_source = strategy
                self.logger.debug(f"[aiohttp] {item.title[:50]}")
            else:
                aiohttp_failed.append(item)

        if aiohttp_failed:
            self.logger.info(
                f"Phase 1 aiohttp: {total - len(aiohttp_failed)}/{total} ok, "
                f"{len(aiohttp_failed)} → headless"
            )

        # Strategy 2: Headless Chrome (batch, single browser)
        if aiohttp_failed and self.use_headless:
            headless_failed = await self._phase1_fetch_browser_batch(
                aiohttp_failed, pages_dir, headless=True, date=date
            )
        else:
            headless_failed = aiohttp_failed

        # Strategy 3: Headed Chrome (batch, single browser)
        if headless_failed and self.use_headed:
            headed_failed = await self._phase1_fetch_browser_batch(
                headless_failed, pages_dir, headless=False, date=date
            )
        else:
            headed_failed = headless_failed

        # Remaining failures
        for item in headed_failed:
            item.enrichment_source = "fetch_failed"
            item.article_text = None
            item.article_images = []
            item.article_summary = None
            item.screenshot_image = None
            self.logger.info(f"[fetch_failed] {item.title[:50]} ({item.url})")

    async def _phase1_fetch_one_aiohttp(self, item, pages_dir: Path) -> Optional[str]:
        """Try aiohttp fetch. On success save HTML to disk, return strategy name.
        Returns None if fetch fails OR if the HTML has no extractable content,
        so the item falls through to headless/headed."""
        try:
            html = await self._fetch_page(item.url)
            if html:
                html_path = pages_dir / f"{item.source_id}.html"
                if self.save_fetched_html:
                    html_path.write_text(html, encoding="utf-8", errors="replace")
                    self.logger.debug(f"HTML saved: {html_path} ({len(html)} bytes)")
                # Verify the HTML actually contains extractable content.
                # If not, return None so headless/headed gets a chance.
                if self._extract_text(html, item.url or ""):
                    return "aiohttp"
                self.logger.debug(
                    f"[aiohttp] HTML has no extractable content, will try browser: "
                    f"{item.title[:50]}"
                )
                return None
        except Exception:
            pass
        return None

    async def _phase1_fetch_browser_batch(
        self, items: list, pages_dir: Path, headless: bool, date: str
    ) -> list:
        """Fetch multiple URLs with a single Playwright browser instance.

        Returns list of items that still failed (for next fallback).
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.info("playwright not installed, skipping browser batch")
            return items

        launch_kwargs = {"headless": headless, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        strategy_name = "headless" if headless else "headed"
        failed = []
        image_dir = Path(f"data/{date}/images")
        image_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**launch_kwargs)
                try:
                    for item in items:
                        try:
                            context = await browser.new_context(
                                user_agent=random.choice(_USER_AGENTS),
                                viewport={"width": 1280, "height": 720},
                                locale="en-US",
                            )
                            page = await context.new_page()
                            try:
                                from playwright_stealth import stealth_async
                                await stealth_async(page)
                            except ImportError:
                                pass

                            if self.request_delay > 0:
                                await asyncio.sleep(self.request_delay)

                            await page.goto(
                                item.url,
                                wait_until="domcontentloaded",
                                timeout=self.request_timeout * 1000,
                            )
                            await asyncio.sleep(1.5)

                            # Check for anti-bot blocks
                            block_reason = await self._check_anti_bot(page, item.url, self.logger)
                            if block_reason:
                                self.logger.debug(
                                    f"[{strategy_name}] anti-bot: {block_reason} — {item.url}"
                                )
                                await context.close()
                                continue

                            # Save HTML
                            html = await page.content()
                            if html and len(html) > 500:
                                html_path = pages_dir / f"{item.source_id}.html"
                                if self.save_fetched_html:
                                    html_path.write_text(html, encoding="utf-8", errors="replace")
                                item.enrichment_source = strategy_name
                                self.logger.debug(
                                    f"[{strategy_name}] {item.title[:50]} ({len(html)} bytes)"
                                )

                                # Capture screenshot
                                if self.screenshot_enabled:
                                    screenshot_dest = image_dir / f"{item.source_id}_screenshot.jpg"
                                    try:
                                        await page.screenshot(
                                            path=str(screenshot_dest),
                                            type="jpeg", quality=85,
                                        )
                                        item.screenshot_image = f"images/{item.source_id}_screenshot.jpg"
                                    except Exception:
                                        pass
                            else:
                                self.logger.debug(
                                    f"[{strategy_name}] empty/short HTML for {item.url}"
                                )
                            await context.close()
                        except Exception as e:
                            self.logger.debug(
                                f"[{strategy_name}] failed for {item.url}: {e}"
                            )
                            try:
                                await context.close()
                            except Exception:
                                pass
                finally:
                    await browser.close()
        except Exception as e:
            self.logger.debug(f"Browser batch failed: {e}")
            # If the entire browser launch failed, all items fail
            for item in items:
                if item.enrichment_source is None:
                    failed.append(item)
            return failed

        # Collect items that still have no strategy (failed in the loop)
        for item in items:
            if item.enrichment_source != strategy_name and item not in failed:
                failed.append(item)
        return failed

    # ── Phase 2: Extract from on-disk HTML ─────────────────────

    async def _phase2_extract_all(self, items: list, date: str):
        """Run Phase 2 extraction for all items that have HTML on disk."""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._phase2_extract_one(item, date, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                self.logger.info(f"Phase 2 extraction failed for item {items[i].source_id}: {r}")

    async def _phase2_extract_one(self, item, date: str, semaphore: asyncio.Semaphore):
        """Read HTML from disk and run full extraction pipeline."""
        async with semaphore:
            try:
                pages_dir = self._pages_dir(date)
                html_path = pages_dir / f"{item.source_id}.html"

                if not html_path.exists():
                    item.enrichment_source = "fetch_failed"
                    return

                html = html_path.read_text(encoding="utf-8", errors="replace")
                image_dir = Path(f"data/{date}/images")
                image_dir.mkdir(parents=True, exist_ok=True)

                # Extract text
                article_text = self._extract_text(html, item.url or "")
                if not article_text:
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.enrichment_source = "extraction_failed"
                    self.logger.debug(
                        f"Phase 2 extraction empty: {item.title[:50]}"
                    )
                    return

                # Extract images from HTML
                image_urls = self._extract_images(html, item.url or "")

                # Download page images
                page_images = []
                if image_urls:
                    page_images = await self._download_images(
                        image_urls, image_dir, str(item.source_id)
                    )

                # Bing image search
                bing_images = []
                if self.bing_image_search and item.title:
                    bing_images = await self._search_bing_images(
                        item.title, item.url or "", image_dir, str(item.source_id)
                    )

                # Combine images
                all_images = page_images + bing_images

                # Screenshot: reuse from Phase 1 if exists, otherwise capture now
                screenshot_image = item.screenshot_image  # may have been set in Phase 1
                if not screenshot_image and self.screenshot_enabled:
                    screenshot_filename = f"{item.source_id}_screenshot.jpg"
                    if (image_dir / screenshot_filename).exists():
                        screenshot_image = f"images/{screenshot_filename}"
                    elif item.url:
                        screenshot_image = await self._capture_screenshot(
                            item.url, image_dir, str(item.source_id)
                        )
                    item.screenshot_image = screenshot_image

                # LLM summary
                article_summary = self._summarize(article_text, item.title)

                # Populate item
                item.article_text = article_text[:self.max_text_length]
                item.article_images = all_images
                item.article_summary = article_summary
                # Keep enrichment_source from Phase 1 if set; otherwise mark as downloaded_page
                if not item.enrichment_source or item.enrichment_source == "fetch_failed":
                    item.enrichment_source = "downloaded_page"

                # Build image_candidates
                item.image_candidates = []
                for img_path in page_images:
                    item.image_candidates.append({"path": img_path, "source": "page"})
                for img_path in bing_images:
                    item.image_candidates.append({"path": img_path, "source": "bing"})
                if screenshot_image:
                    item.image_candidates.append({"path": screenshot_image, "source": "screenshot"})

                self.logger.info(
                    f"[{item.enrichment_source}] {item.title[:50]} — "
                    f"{len(article_text)} chars, "
                    f"page={len(page_images)} bing={len(bing_images)} "
                    f"ss={'Y' if screenshot_image else 'N'}"
                )

            except Exception as e:
                self.logger.info(f"Phase 2 failed for {item.url}: {e}", exc_info=True)
                item.article_text = None
                item.article_images = []
                item.article_summary = None
                item.enrichment_source = "error"
                item.enrichment_error = f"{type(e).__name__}: {e}"
                item.screenshot_image = None

    async def _fetch_page(self, url: str) -> Optional[str]:
        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None

        @retry(
            stop=stop_after_attempt(self.retry_count),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            reraise=True,
        )
        async def _do_fetch():
            headers = _make_headers()  # fresh UA per attempt
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
                trust_env=True,
            ) as session:
                async with session.get(
                    url, allow_redirects=True, max_redirects=5,
                ) as resp:
                    if resp.status == 429:
                        self.logger.debug(f"HTTP 429 (rate-limited) for {url}")
                        raise aiohttp.ClientError(f"Rate limited: {url}")
                    if resp.status in (403, 401):
                        # Likely WAF / bot challenge. Not retried — headless
                        # fallback has a better chance than more aiohttp hits.
                        self.logger.debug(
                            f"HTTP {resp.status} (likely bot challenge) for {url}"
                        )
                        return None
                    if resp.status != 200:
                        self.logger.debug(f"HTTP {resp.status} for {url}")
                        raise aiohttp.ClientError(f"HTTP {resp.status} for {url}")
                    ct = resp.headers.get("Content-Type", "")
                    if "text/html" not in ct and "application/xhtml" not in ct:
                        self.logger.debug(f"Non-HTML content type: {ct} for {url}")
                        return None
                    body = await resp.content.read(10 * 1024 * 1024)
                    return body.decode("utf-8", errors="replace")

        try:
            return await _do_fetch()
        except Exception as e:
            self.logger.debug(f"Fetch failed for {url}: {e}")
            return None

    async def _capture_screenshot(self, url: str, image_dir: Path, source_id: str) -> Optional[str]:
        """Capture a webpage screenshot using headless Chrome (standalone, no text extraction)."""
        if not self.screenshot_enabled or not self.use_headless:
            return None
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        filename = f"{source_id}_screenshot.jpg"
        dest = image_dir / filename

        launch_kwargs = {"headless": True, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                )
                page = await context.new_page()
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except ImportError:
                    pass
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    await asyncio.sleep(1.5)
                    await page.screenshot(path=str(dest), type="jpeg", quality=85)
                    self.logger.debug(f"Screenshot captured: {dest}")
                    return f"images/{filename}"
                except Exception as e:
                    self.logger.debug(f"Screenshot capture failed for {url}: {e}")
                    return None
                finally:
                    await browser.close()
        except Exception as e:
            self.logger.debug(f"Headless Chrome failed for screenshot of {url}: {e}")
            return None

    @staticmethod
    async def _check_anti_bot(page, url: str, logger) -> Optional[str]:
        """Detect anti-bot challenges on the page. Returns reason or None."""
        try:
            title = await page.title()
            url_after = page.url

            # Cloudflare challenge
            if "just a moment" in title.lower() or "checking your browser" in title.lower():
                return "Cloudflare challenge page"
            cf_meta = await page.query_selector('meta[name="cf-beacon"]')
            if cf_meta:
                # cf-beacon present but content extracted — not necessarily blocked
                pass

            # Check for common challenge frames
            cf_iframe = await page.query_selector('iframe[src*="challenges.cloudflare.com"]')
            if cf_iframe:
                return "Cloudflare Turnstile/Challenge iframe"

            # Generic CAPTCHA indicators
            captcha = await page.query_selector('[class*="captcha"], [id*="captcha"], .g-recaptcha, .h-captcha')
            if captcha:
                return "CAPTCHA detected"

            # Login/paywall redirects
            parsed_before = urlparse(url)
            parsed_after = urlparse(url_after)
            if parsed_after.hostname and parsed_before.hostname:
                if parsed_after.hostname != parsed_before.hostname:
                    if any(kw in parsed_after.hostname for kw in ("login", "auth", "signin", "subscribe", "paywall")):
                        return f"Redirected to {parsed_after.hostname}"

            # JS-rendered empty shell: very few DOM nodes
            node_count = await page.evaluate("document.querySelectorAll('*').length")
            if node_count < 15:
                return f"Near-empty DOM ({node_count} nodes)"

            return None
        except Exception:
            return None

    async def _fetch_with_headless(self, url: str, screenshot_path: Optional[str] = None) -> Optional[str]:
        """Fetch page using Playwright headless Chrome with stealth anti-detection."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.info("playwright not installed, run: uv add playwright && playwright install chromium")
            return None

        launch_kwargs = {"headless": True, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                )
                page = await context.new_page()
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except ImportError:
                    pass

                # Capture console messages for debugging
                console_msgs = []
                page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    await asyncio.sleep(1.5)

                    # Check for anti-bot blocks
                    block_reason = await self._check_anti_bot(page, url, self.logger)
                    if block_reason:
                        self.logger.debug(f"Headless anti-bot: {block_reason} — {url}")
                        # Log last few console messages for diagnosis
                        for msg in console_msgs[-5:]:
                            self.logger.debug(f"  console: {msg}")
                        return None

                    if screenshot_path and self.screenshot_enabled:
                        try:
                            await page.screenshot(path=screenshot_path, type="jpeg", quality=85)
                        except Exception as e:
                            self.logger.debug(f"Screenshot capture failed: {e}")
                    html = await page.content()
                    if html and len(html) > 500:
                        return html
                    return None
                finally:
                    await browser.close()
        except Exception as e:
            self.logger.debug(f"Headless Chrome failed for {url}: {e}")
            return None

    async def _fetch_with_headed(self, url: str) -> Optional[str]:
        """Fetch page using Playwright headed Chrome (visible browser window)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.info("playwright not installed, skipping headed Chrome")
            return None

        launch_kwargs = {"headless": False, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1280, "height": 720},
                    locale="en-US",
                )
                page = await context.new_page()
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except ImportError:
                    pass

                # Capture console messages for debugging
                console_msgs = []
                page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    await asyncio.sleep(3.0)

                    # Check for anti-bot blocks
                    block_reason = await self._check_anti_bot(page, url, self.logger)
                    if block_reason:
                        self.logger.debug(f"Headed anti-bot: {block_reason} — {url}")
                        for msg in console_msgs[-5:]:
                            self.logger.debug(f"  console: {msg}")
                        return None

                    html = await page.content()
                    if html and len(html) > 500:
                        return html
                    return None
                finally:
                    await browser.close()
        except Exception as e:
            self.logger.debug(f"Headed Chrome failed for {url}: {e}")
            return None

    async def _search_bing_images(
        self, title: str, url: str, image_dir: Path, source_id: str
    ) -> List[str]:
        """Search Bing Images for article title, download top results."""
        domain = urlparse(url).hostname or ""
        query = f"{title} {domain}".strip()
        search_url = f"https://www.bing.com/images/search?q={query}&first=1"

        try:
            # Use headless Chrome — Bing blocks plain aiohttp with an empty page.
            html = await self._fetch_with_headless(search_url)
            if not html:
                # Fallback to aiohttp if headless unavailable
                html = await self._fetch_page(search_url)
            if not html:
                return []

            image_urls = self._extract_bing_image_urls(html)
            if not image_urls:
                return []

            image_urls = image_urls[:self.bing_max_results]
            local_paths = await self._download_images(image_urls, image_dir, f"{source_id}_bing")
            return local_paths
        except Exception as e:
            self.logger.info(f"Bing image search failed for '{title}': {e}")
            return []

    def _extract_bing_image_urls(self, html: str) -> List[str]:
        """Extract image URLs from Bing Images search results HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")
            urls = []
            # Bing stores image URLs in m attribute on <a class="iusc"> tags
            for a_tag in soup.find_all("a", class_="iusc", limit=self.bing_max_results * 2):
                m_attr = a_tag.get("m")
                if m_attr:
                    try:
                        m_data = json.loads(m_attr)
                        img_url = m_data.get("murl") or m_data.get("turl")
                        if img_url and img_url not in urls:
                            urls.append(img_url)
                    except json.JSONDecodeError:
                        continue
            # Fallback: look for img tags with src containing "bing.com/th"
            if not urls:
                for img in soup.find_all("img", limit=self.bing_max_results * 3):
                    src = img.get("src") or ""
                    if "bing.com/th" in src and src not in urls:
                        urls.append(src)
            return urls[:self.bing_max_results]
        except Exception as e:
            self.logger.debug(f"Bing image URL extraction failed: {e}")
            return []

    def _extract_text(self, html: str, base_url: str) -> Optional[str]:
        try:
            text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True)
            if text and len(text.strip()) > 100:
                return text.strip()[:self.max_text_length]
            return None
        except Exception as e:
            self.logger.debug(f"trafilatura failed: {e}")
            return None

    def _extract_images(self, html: str, base_url: str) -> List[str]:
        try:
            soup = BeautifulSoup(html, "lxml")
            images = []

            # 1. og:image
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                images.append(urljoin(base_url, og_img["content"]))

            # 2. twitter:image
            tw_img = soup.find("meta", attrs={"name": "twitter:image"})
            if tw_img and tw_img.get("content"):
                img_url = urljoin(base_url, tw_img["content"])
                if img_url not in images:
                    images.append(img_url)

            # 3. Article body images
            article = soup.find("article") or soup.find(class_=re.compile(r"article|post|content|entry", re.I))
            if article:
                for img in article.find_all("img", limit=self.max_images * 2):
                    src = img.get("src") or img.get("data-src")
                    if src:
                        img_url = urljoin(base_url, src)
                        # Skip tiny images (icons, spacers)
                        width = img.get("width", "")
                        height = img.get("height", "")
                        if width and height:
                            try:
                                if int(width) < 100 or int(height) < 100:
                                    continue
                            except ValueError:
                                pass
                        if img_url not in images:
                            images.append(img_url)

            # Filter out common non-content patterns
            filtered = []
            skip_patterns = ["avatar", "logo", "icon", "badge", "pixel", "spacer", "tracking", "analytics", "svg", "camo.githubusercontent.com"]
            for img_url in images:
                if not any(p in img_url.lower() for p in skip_patterns):
                    filtered.append(img_url)
                else:
                    self.logger.debug(f"Image filtered out (matched pattern): {img_url}")

            result = filtered[:self.max_images]
            self.logger.debug(f"Extracted {len(result)} image URLs from {base_url}: {result}")
            return result
        except Exception as e:
            self.logger.debug(f"Image extraction failed: {e}")
            return []

    async def _download_images(self, urls: List[str], image_dir: Path, source_id: str) -> List[str]:
        local_paths = []
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)

        async def _fetch_one(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
            """Download one image; return bytes or None. Short reads return None."""
            headers = _make_headers()
            headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    self.logger.warning(f"Image HTTP {resp.status} for {url}")
                    return None

                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > self.max_image_size:
                    self.logger.warning(f"Image too large ({cl} bytes) for {url}")
                    return None

                data = await resp.read()
                if len(data) > self.max_image_size:
                    self.logger.warning(f"Image read too large ({len(data)} bytes) for {url}")
                    return None

                # Guard against CDN-induced short reads: compare against
                # Content-Length and reject if we got notably less. PIL on a
                # severely truncated WebP raises a cryptic "could not create
                # decoder object", so catch it here with a clearer message.
                if cl and len(data) < int(cl) * 0.9:
                    self.logger.warning(
                        f"Short read for {url}: got {len(data)} / {cl} bytes"
                    )
                    return None
                return data

        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            for idx, url in enumerate(urls):
                try:
                    filename = f"{source_id}_{idx}.jpg"
                    dest = image_dir / filename
                    if dest.exists():
                        local_paths.append(f"images/{filename}")
                        continue

                    # One retry on short-read / transient CDN flake.
                    data = await _fetch_one(session, url)
                    if data is None:
                        self.logger.debug(f"Image fetch retry: {url}")
                        data = await _fetch_one(session, url)
                    if data is None:
                        self.logger.warning(f"Image fetch failed after retry: {url}")
                        continue

                    self.logger.debug(
                        f"Image fetched {len(data)} bytes from {url}"
                    )
                    try:
                        img = Image.open(io.BytesIO(data))
                        img = img.convert("RGB")

                        if img.width > self.image_target_width or img.height > self.image_target_height:
                            img.thumbnail(
                                (self.image_target_width, self.image_target_height),
                                Image.Resampling.LANCZOS,
                            )

                        img.save(dest, "JPEG", quality=85)
                        local_paths.append(f"images/{filename}")
                        self.logger.debug(
                            f"Image saved: {dest} ({img.width}x{img.height})"
                        )
                    except Exception as e:
                        self.logger.warning(f"Image decode failed for {url}: {e}")

                except Exception as e:
                    self.logger.warning(f"Image download failed for {url}: {e}")

        return local_paths

    def _load_image_selection(self, content: ContentPackage, date: str) -> set:
        """Load image_selection.json if it exists. Returns set of source_ids with user selections."""
        sel_path = Path(f"data/{date}/image_selection.json")
        if not sel_path.exists():
            return set()
        try:
            with open(sel_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            selected = set()
            for item in content.items:
                entry = data.get("items", {}).get(str(item.source_id))
                if entry and entry.get("selected_image"):
                    item.article_images = [entry["selected_image"]]
                    selected.add(str(item.source_id))
                    self.logger.debug(f"Image selection loaded for {item.source_id}: {entry['selected_image']}")
            return selected
        except Exception as e:
            self.logger.info(f"Failed to load image selection: {e}")
            return set()

    def _generate_image_selection(self, content: ContentPackage, date: str):
        """Generate image_selection.json for user review."""
        sel_path = Path(f"data/{date}/image_selection.json")
        if sel_path.exists():
            return  # Already exists — user has edited it, don't overwrite

        data = {"date": date, "items": {}}
        for item in content.items:
            if not item.image_candidates:
                continue
            selected = item.image_candidates[0]["path"] if item.image_candidates else None
            data["items"][str(item.source_id)] = {
                "title": item.title,
                "url": item.url,
                "candidates": item.image_candidates,
                "selected_image": selected,
            }

        if not data["items"]:
            return

        sel_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sel_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Generated image selection file: {sel_path}")

    def _summarize(self, article_text: str, title: str) -> Optional[str]:
        if not self._summarize_prompt:
            self.logger.info("Summarize prompt not loaded, skipping LLM summary")
            return None

        try:
            prompt = render_prompt(
                self._summarize_prompt,
                title=title,
                article_text=article_text[:self.max_text_length],
            )

            # Split on <!-- SYSTEM_CUT --> if present
            if "<!-- SYSTEM_CUT -->" in prompt:
                parts = prompt.split("<!-- SYSTEM_CUT -->", 1)
                system_msg = parts[0].strip()
                user_msg = parts[1].strip()
            else:
                system_msg = "你是一位技术内容分析师。"
                user_msg = prompt

            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=self.llm_max_tokens,
                temperature=self.llm_temperature,
            )

            summary = response.choices[0].message.content.strip()
            if not summary or len(summary) < 10:
                return None
            return summary

        except Exception as e:
            self.logger.info(f"LLM summarization failed for '{title}': {e}")
            return None

    def _save_to_cache(self, content: ContentPackage, cache_path: Path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "date": content.date,
            "items": {}
        }
        for item in content.items:
            if item.article_text is not None or item.article_summary is not None:
                data["items"][str(item.source_id)] = {
                    "article_text": item.article_text,
                    "article_images": item.article_images,
                    "article_summary": item.article_summary,
                    "enrichment_source": item.enrichment_source,
                    "enrichment_error": item.enrichment_error,
                    "logo_image": item.logo_image,
                    "screenshot_image": item.screenshot_image,
                    "image_candidates": item.image_candidates,
                }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.debug(f"Saved enrichment cache to {cache_path}")

    def _load_from_cache(self, content: ContentPackage, cache_path: Path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items_cache = data.get("items", {})
            for item in content.items:
                cached = items_cache.get(str(item.source_id))
                if cached:
                    item.article_text = cached.get("article_text")
                    item.article_images = cached.get("article_images", [])
                    item.article_summary = cached.get("article_summary")
                    source = cached.get("enrichment_source") or "legacy"
                    if source == "manual_override":
                        source = "downloaded_page"
                    elif source == "none" and not cached.get("article_text"):
                        source = None  # let _classify_items re-evaluate
                    item.enrichment_source = source
                    item.enrichment_error = cached.get("enrichment_error")
                    item.logo_image = cached.get("logo_image")
                    item.screenshot_image = cached.get("screenshot_image")
                    item.image_candidates = cached.get("image_candidates", [])
            loaded = sum(1 for item in content.items if item.article_text is not None or item.article_summary is not None)
            self.logger.debug(f"Loaded {loaded} cached enrichments from {cache_path}")
        except Exception as e:
            self.logger.info(f"Failed to load enrichment cache: {e}")
