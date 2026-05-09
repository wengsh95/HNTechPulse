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

    def enrich(self, content: ContentPackage, date: str) -> ContentPackage:
        if not self.enabled:
            self.logger.info("Article enrichment disabled, skipping")
            return content

        self.logger.info(f"Enriching {len(content.items)} items...")

        # Load manual overrides first (user-filled content for failed items)
        overridden_ids = self._load_manual_overrides(content, date)

        # Load image selections second (user-chosen images)
        image_selected_ids = self._load_image_selection(content, date)

        # Load checkpoint
        cache_path = Path(f"data/{date}/enrichment.json")
        if cache_path.exists():
            self._load_from_cache(content, cache_path)

        # Check if all items already enriched
        pending = [
            item for item in content.items
            if item.url and item.article_text is None and item.article_summary is None
            and str(item.source_id) not in overridden_ids
        ]
        if not pending:
            self.logger.info("All items already enriched, skipping text enrichment")

        # Backfill missing images (screenshot/logo) even for cached items
        image_pending = [
            item for item in content.items
            if item.url and self._needs_image_backfill(item, date)
            and str(item.source_id) not in image_selected_ids
        ]
        if image_pending:
            self.logger.info(f"Image backfill needed: {len(image_pending)}/{len(content.items)} items")
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._backfill_images(image_pending, date))
                    future.result()
            except RuntimeError:
                asyncio.run(self._backfill_images(image_pending, date))
            # Persist backfilled image paths to cache
            self._save_to_cache(content, cache_path)

        if not pending and not image_pending:
            # Still generate selection/override files even if no fetching needed
            self._generate_image_selection(content, date)
            self._generate_manual_override(content, date)
            return content

        self.logger.info(f"Pending text enrichment: {len(pending)}/{len(content.items)} items")

        # Run async enrichment
        try:
            loop = asyncio.get_running_loop()
            # Already inside an async context — run in a background thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._enrich_items(content, date))
                future.result()
        except RuntimeError:
            # No running loop — this is the normal CLI path
            asyncio.run(self._enrich_items(content, date))

        # Generate image selection file for user review
        self._generate_image_selection(content, date)

        # Generate manual override template for failed items
        self._generate_manual_override(content, date)

        # Save checkpoint
        self._save_to_cache(content, cache_path)
        self.logger.info("Enrichment complete")
        return content

    async def _enrich_items(self, content: ContentPackage, date: str):
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._enrich_one(item, date, semaphore) for item in content.items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                self.logger.info(f"Enrichment failed for item {i}: {r}")

    def _needs_image_backfill(self, item, date: str) -> bool:
        """Check if an item is missing screenshot on disk."""
        image_dir = Path(f"data/{date}/images")
        if self.screenshot_enabled and not item.screenshot_image:
            if not (image_dir / f"{item.source_id}_screenshot.jpg").exists():
                return True
        return False

    async def _backfill_images(self, items: list, date: str):
        """Download missing screenshots and logos for already-enriched items."""
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._backfill_one(item, date, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                self.logger.info(f"Image backfill failed for item {i}: {r}")

    async def _backfill_one(self, item, date: str, semaphore: asyncio.Semaphore):
        image_dir = Path(f"data/{date}/images")
        image_dir.mkdir(parents=True, exist_ok=True)
        async with semaphore:
            try:
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)

                # Screenshot
                if self.screenshot_enabled and not item.screenshot_image:
                    screenshot_filename = f"{item.source_id}_screenshot.jpg"
                    if not (image_dir / screenshot_filename).exists():
                        ss = await self._capture_screenshot(item.url, image_dir, str(item.source_id))
                        if ss:
                            item.screenshot_image = ss

            except Exception as e:
                self.logger.debug(f"Image backfill failed for {item.url}: {e}")

    async def _enrich_one(self, item, date: str, semaphore: asyncio.Semaphore):
        if not item.url:
            return
        if item.article_text is not None or item.article_summary is not None:
            return

        # Bypass domains that are known to be un-scrapable (Twitter/X, etc.).
        # Matches bare domain AND subdomains (twitter.com ⇒ mobile.twitter.com).
        if self.skip_domains:
            host = (urlparse(item.url).hostname or "").lower().lstrip(".")
            if any(host == d or host.endswith("." + d) for d in self.skip_domains):
                self.logger.debug(
                    f"[skip] {item.title[:50]} — domain {host} in skip_domains"
                )
                item.article_text = None
                item.article_images = []
                item.article_summary = None
                item.enrichment_source = "skipped"
                item.screenshot_image = None
                return

        async with semaphore:
            try:
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)

                article_text = None
                image_urls = []
                strategy = "none"
                short_title = item.title[:50]

                # Strategy 1: aiohttp (fast, non-blocking)
                html = await self._fetch_page(item.url)
                if html:
                    article_text = self._extract_text(html, item.url)
                    image_urls = self._extract_images(html, item.url)
                    if article_text:
                        strategy = "aiohttp"
                    else:
                        # HTML came back but trafilatura found <100 chars —
                        # usually a JS-only shell, paywall, or CF challenge page.
                        self.logger.debug(
                            f"aiohttp got HTML but extraction empty "
                            f"({len(html)} bytes): {item.url}"
                        )

                # Strategy 2: Headless Chrome (real browser fingerprint)
                if not article_text and self.use_headless:
                    self.logger.debug(
                        f"[1/3] aiohttp miss → headless Chrome: {short_title}"
                    )
                    image_dir = Path(f"data/{date}/images")
                    image_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_filename = f"{item.source_id}_screenshot.jpg"
                    screenshot_dest = str(image_dir / screenshot_filename) if self.screenshot_enabled else None
                    html = await self._fetch_with_headless(item.url, screenshot_path=screenshot_dest)
                    if html:
                        article_text = self._extract_text(html, item.url)
                        image_urls = self._extract_images(html, item.url)
                        if article_text:
                            strategy = "headless"

                # Strategy 3: Headed Chrome (visible browser window, for JS-heavy/anti-bot sites)
                if not article_text and self.use_headed:
                    self.logger.debug(
                        f"[2/3] headless miss → headed Chrome: {short_title}"
                    )
                    html = await self._fetch_with_headed(item.url)
                    if html:
                        article_text = self._extract_text(html, item.url)
                        image_urls = self._extract_images(html, item.url)
                        if article_text:
                            strategy = "headed"

                # Strategy 4: Give up
                if not article_text:
                    self.logger.info(
                        f"[3/3] All strategies exhausted: {short_title} ({item.url})"
                    )
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.enrichment_source = "none"
                    item.logo_image = None
                    item.screenshot_image = None
                    return

                # Download images
                image_dir = Path(f"data/{date}/images")
                image_dir.mkdir(parents=True, exist_ok=True)
                local_images = []
                if image_urls:
                    local_images = await self._download_images(
                        image_urls, image_dir, str(item.source_id)
                    )

                # Bing image search fallback if no page images found
                bing_images = []
                if not local_images and self.bing_image_search and item.title:
                    self.logger.debug(f"No page images, trying Bing search: {short_title}")
                    bing_images = await self._search_bing_images(
                        item.title, item.url, image_dir, str(item.source_id)
                    )
                    if bing_images:
                        local_images = bing_images
                        self.logger.info(f"Bing search found {len(bing_images)} images for {short_title}")

                # Screenshot: check if headless captured one
                screenshot_image = None
                if self.screenshot_enabled:
                    screenshot_filename = f"{item.source_id}_screenshot.jpg"
                    if (image_dir / screenshot_filename).exists():
                        screenshot_image = f"images/{screenshot_filename}"
                        self.logger.debug(f"Screenshot found: {screenshot_image}")
                    else:
                        # No screenshot on disk — capture one with headless Chrome
                        screenshot_image = await self._capture_screenshot(
                            item.url, image_dir, str(item.source_id)
                        )

                # LLM summarize
                article_summary = self._summarize(article_text, item.title)

                item.article_text = article_text[:self.max_text_length]
                item.article_images = local_images
                item.screenshot_image = screenshot_image
                item.article_summary = article_summary
                item.enrichment_source = strategy

                # Build image_candidates list
                item.image_candidates = []
                for img_path in local_images:
                    source = "bing" if img_path in bing_images else "page"
                    item.image_candidates.append({"path": img_path, "source": source})
                if screenshot_image:
                    item.image_candidates.append({"path": screenshot_image, "source": "screenshot"})

                self.logger.info(
                    f"[{strategy}] {short_title} — "
                    f"{len(item.article_text)} chars, {len(local_images)} imgs"
                    f", ss={'Y' if screenshot_image else 'N'}"
                )

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                self.logger.info(f"Failed to enrich {item.url}: {e}", exc_info=True)
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
            self.logger.debug(f"Bing image search failed for '{title}': {e}")
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

    def _load_manual_overrides(self, content: ContentPackage, date: str) -> set:
        """Load manual_override.json if it exists. Returns set of source_ids that were overridden."""
        override_path = Path(f"data/{date}/manual_override.json")
        if not override_path.exists():
            return set()
        try:
            with open(override_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            overridden = set()
            for item in content.items:
                entry = data.get("items", {}).get(str(item.source_id))
                if entry and entry.get("article_text"):
                    item.article_text = entry["article_text"]
                    item.article_images = entry.get("article_images", [])
                    item.article_summary = entry.get("article_summary")
                    item.enrichment_source = "manual_override"
                    overridden.add(str(item.source_id))
                    self.logger.info(f"Manual override loaded for {item.source_id}")
            return overridden
        except Exception as e:
            self.logger.info(f"Failed to load manual overrides: {e}")
            return set()

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

    def _generate_manual_override(self, content: ContentPackage, date: str):
        """Generate manual_override.json template for items that failed enrichment."""
        override_path = Path(f"data/{date}/manual_override.json")

        # Load existing overrides to preserve user edits
        existing = {}
        if override_path.exists():
            try:
                with open(override_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        failed_items = {
            str(item.source_id): item
            for item in content.items
            if item.enrichment_source in ("none", "error")
        }
        if not failed_items and not existing:
            return

        data = {"date": date, "items": {}}
        all_ids = set(failed_items.keys()) | set(existing.get("items", {}).keys())

        for sid in all_ids:
            # Preserve existing user edits
            if sid in existing.get("items", {}):
                existing_entry = existing["items"][sid]
                if existing_entry.get("article_text"):
                    data["items"][sid] = existing_entry
                    continue

            # Generate template for failed item
            item = failed_items.get(sid)
            if item:
                data["items"][sid] = {
                    "title": item.title,
                    "url": item.url,
                    "article_text": "",
                    "article_images": [],
                    "article_summary": "",
                }

        if not data["items"]:
            return

        override_path.parent.mkdir(parents=True, exist_ok=True)
        with open(override_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Generated manual override template: {override_path} ({len(data['items'])} items)")

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
                    # Pre-tagging caches have no source field — mark as "legacy"
                    # so it's distinguishable from genuinely missing data.
                    item.enrichment_source = cached.get("enrichment_source") or "legacy"
                    item.enrichment_error = cached.get("enrichment_error")
                    item.logo_image = cached.get("logo_image")
                    item.screenshot_image = cached.get("screenshot_image")
                    item.image_candidates = cached.get("image_candidates", [])
            loaded = sum(1 for item in content.items if item.article_text is not None or item.article_summary is not None)
            self.logger.debug(f"Loaded {loaded} cached enrichments from {cache_path}")
        except Exception as e:
            self.logger.info(f"Failed to load enrichment cache: {e}")
