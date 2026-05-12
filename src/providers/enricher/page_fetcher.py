import asyncio
import logging
import platform
import random
import shutil
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

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


class PageFetcher:
    """Handles HTTP and browser-based page fetching with fallback strategies."""

    def __init__(
        self,
        logger: logging.Logger,
        retry_count: int = 3,
        request_timeout: int = 15,
        request_delay: float = 0.5,
        use_headless: bool = True,
        use_headed: bool = True,
        screenshot_enabled: bool = True,
        save_fetched_html: bool = True,
        browser_executable: Optional[str] = None,
    ):
        self.logger = logger
        self.retry_count = retry_count
        self.request_timeout = request_timeout
        self.request_delay = request_delay
        self.use_headless = use_headless
        self.use_headed = use_headed
        self.screenshot_enabled = screenshot_enabled
        self.save_fetched_html = save_fetched_html
        self.browser_executable = browser_executable

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a page via aiohttp with retry."""
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
            headers = _make_headers()
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

    async def fetch_browser_batch(
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

                            block_reason = await check_anti_bot(page, item.url, self.logger)
                            if block_reason:
                                self.logger.debug(
                                    f"[{strategy_name}] anti-bot: {block_reason} — {item.url}"
                                )
                                await context.close()
                                continue

                            html = await page.content()
                            if html and len(html) > 500:
                                html_path = pages_dir / f"{item.source_id}.html"
                                if self.save_fetched_html:
                                    html_path.write_text(html, encoding="utf-8", errors="replace")
                                item.enrichment_source = strategy_name
                                self.logger.debug(
                                    f"[{strategy_name}] {item.title[:50]} ({len(html)} bytes)"
                                )

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
            for item in items:
                if item.enrichment_source is None:
                    failed.append(item)
            return failed

        for item in items:
            if item.enrichment_source != strategy_name and item not in failed:
                failed.append(item)
        return failed

    async def capture_screenshot(self, url: str, image_dir: Path, source_id: str) -> Optional[str]:
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

    async def fetch_with_headless(self, url: str, screenshot_path: Optional[str] = None) -> Optional[str]:
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

                console_msgs = []
                page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    await asyncio.sleep(1.5)

                    block_reason = await check_anti_bot(page, url, self.logger)
                    if block_reason:
                        self.logger.debug(f"Headless anti-bot: {block_reason} — {url}")
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

    async def fetch_with_headed(self, url: str) -> Optional[str]:
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

                console_msgs = []
                page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    await asyncio.sleep(3.0)

                    block_reason = await check_anti_bot(page, url, self.logger)
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


async def check_anti_bot(page, url: str, logger) -> Optional[str]:
    """Detect anti-bot challenges on the page. Returns reason or None."""
    try:
        title = await page.title()
        url_after = page.url

        # Cloudflare challenge
        if "just a moment" in title.lower() or "checking your browser" in title.lower():
            return "Cloudflare challenge page"
        cf_meta = await page.query_selector('meta[name="cf-beacon"]')
        if cf_meta:
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
