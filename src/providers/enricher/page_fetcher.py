import asyncio
import logging
import platform
import random
import shutil
import socket
import struct
from pathlib import Path
from typing import Dict, Optional, cast
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


# Third-party DNS servers for fallback resolution
_DNS_SERVERS = [
    ("1.1.1.1", 53),  # Cloudflare
    ("8.8.8.8", 53),  # Google
    ("208.67.222.222", 53),  # OpenDNS
]


def _dns_resolve_sync(
    hostname: str, dns_server: str = "1.1.1.1", port: int = 53, timeout: float = 3.0
) -> Optional[str]:
    """Resolve hostname via a third-party DNS server (synchronous UDP).

    Returns the first A record IP, or None on failure.
    """
    try:
        tx_id = random.randint(0, 65535)
        question = (
            struct.pack("!HHHHHH", tx_id, 0x0100, 1, 0, 0, 0)
            + b"".join(
                struct.pack("B", len(label)) + label.encode()
                for label in hostname.rstrip(".").split(".")
            )
            + b"\x00"
            + struct.pack("!HH", 1, 1)
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(question, (dns_server, port))
            data, _ = sock.recvfrom(512)
        finally:
            sock.close()

        if len(data) < 12:
            return None
        resp_tx_id = struct.unpack("!H", data[:2])[0]
        if resp_tx_id != tx_id:
            return None
        flags = struct.unpack("!H", data[2:4])[0]
        if flags & 0x000F != 0:
            return None

        # Skip header (12) + question section
        idx = 12
        while idx < len(data) and data[idx] != 0:
            idx += data[idx] + 1
        idx += 5  # null + QTYPE(2) + QCLASS(2)

        # Parse answer section
        while idx + 12 <= len(data):
            if data[idx] & 0xC0 == 0xC0:
                idx += 2
            else:
                while idx < len(data) and data[idx] != 0:
                    idx += data[idx] + 1
                idx += 1
            if idx + 10 > len(data):
                break
            rtype_val = struct.unpack("!H", data[idx + 2 : idx + 4])[0]
            rdlen = struct.unpack("!H", data[idx + 8 : idx + 10])[0]
            idx += 10
            if rtype_val == 1 and rdlen == 4 and idx + 4 <= len(data):
                return socket.inet_ntoa(data[idx : idx + 4])
            idx += rdlen
        return None
    except Exception:
        return None


async def _resolve_with_fallback(
    hostname: str, logger: logging.Logger
) -> Optional[str]:
    """Try system DNS first, then fallback to third-party DNS servers.

    Returns IP string, or None if all fail.
    """
    # Try system resolver first
    try:
        loop = asyncio.get_running_loop()
        addrs = await loop.getaddrinfo(hostname, 80)
        for addr in addrs:
            if addr[0] == socket.AF_INET:
                return addr[4][0]
    except Exception:
        pass

    # Fallback to third-party DNS (sync UDP via executor)
    loop = asyncio.get_running_loop()
    for dns_ip, dns_port in _DNS_SERVERS:
        try:
            ip = await loop.run_in_executor(
                None, _dns_resolve_sync, hostname, dns_ip, dns_port, 3.0
            )
            if ip:
                logger.debug(f"DNS fallback: {hostname} → {ip} via {dns_ip}")
                return ip
        except Exception:
            continue

    logger.debug(f"DNS resolution failed for {hostname} (all servers)")
    return None


def _is_pdf_url(url: str) -> bool:
    """Check if a URL likely points to a PDF based on path extension."""
    path = urlparse(url).path.lower()
    return path.endswith(".pdf") or ".pdf?" in path or ".pdf;" in path


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
        if path and (
            Path(path).exists()
            if system == "Windows"
            else shutil.which(path) is not None
        ):
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
        """Fetch a page via aiohttp with retry. Falls back to DNS-over-third-party on network errors."""
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
                    url,
                    allow_redirects=True,
                    max_redirects=5,
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
                    if "application/pdf" in ct:
                        self.logger.debug(f"PDF content type detected: {ct} for {url}")
                        return "__PDF__"
                    if "text/html" not in ct and "application/xhtml" not in ct:
                        self.logger.debug(f"Non-HTML content type: {ct} for {url}")
                        return None
                    body = await resp.content.read(10 * 1024 * 1024)
                    return body.decode("utf-8", errors="replace")

        try:
            return await _do_fetch()
        except Exception as e:
            self.logger.debug(f"Fetch failed for {url}: {e}")

        # DNS fallback: resolve via third-party DNS and retry with IP + Host header
        hostname = parsed.hostname
        if not hostname:
            return None
        ip = await _resolve_with_fallback(hostname, self.logger)
        if not ip:
            return None

        ip_url = f"{parsed.scheme}://{ip}{':' + str(parsed.port) if parsed.port else ''}{parsed.path or '/'}{('?' + parsed.query) if parsed.query else ''}"
        self.logger.debug(
            f"Retrying with resolved IP: {ip_url} (Host: {parsed.hostname})"
        )

        try:
            headers = _make_headers()
            headers["Host"] = str(parsed.hostname or "")
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
                trust_env=True,
            ) as session:
                async with session.get(
                    ip_url,
                    allow_redirects=False,
                ) as resp:
                    if resp.status != 200:
                        return None
                    ct = resp.headers.get("Content-Type", "")
                    if "application/pdf" in ct:
                        self.logger.debug(
                            f"PDF content type (DNS fallback): {ct} for {url}"
                        )
                        return "__PDF__"
                    if "text/html" not in ct and "application/xhtml" not in ct:
                        return None
                    body = await resp.content.read(10 * 1024 * 1024)
                    return body.decode("utf-8", errors="replace")
        except Exception as e:
            self.logger.debug(f"DNS fallback fetch failed for {url}: {e}")
            return None

    async def fetch_pdf(
        self, url: str, max_size: int = 20 * 1024 * 1024
    ) -> Optional[bytes]:
        """Fetch a PDF file via aiohttp. Returns raw bytes or None."""
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
            headers["Accept"] = "application/pdf,*/*;q=0.8"
            timeout = aiohttp.ClientTimeout(total=self.request_timeout * 2)
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
                trust_env=True,
            ) as session:
                async with session.get(
                    url,
                    allow_redirects=True,
                    max_redirects=5,
                ) as resp:
                    if resp.status != 200:
                        self.logger.debug(f"PDF HTTP {resp.status} for {url}")
                        raise aiohttp.ClientError(f"HTTP {resp.status} for {url}")
                    ct = resp.headers.get("Content-Type", "")
                    if "application/pdf" not in ct:
                        self.logger.debug(f"Non-PDF content type: {ct} for {url}")
                        return None
                    cl = resp.headers.get("Content-Length")
                    if cl and int(cl) > max_size:
                        self.logger.debug(f"PDF too large ({cl} bytes) for {url}")
                        return None
                    body = await resp.content.read(max_size)
                    if cl and len(body) < int(cl):
                        raise aiohttp.ClientError(
                            f"Truncated PDF: received {len(body)} of {cl} bytes"
                        )
                    return body

        try:
            return await _do_fetch()
        except Exception as e:
            self.logger.debug(f"PDF fetch failed for {url}: {e}")
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

        launch_kwargs: dict = {"headless": headless, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        strategy_name = "headless" if headless else "headed"
        failed = []
        image_dir = Path(f"data/{date}/images")
        image_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**cast(dict, launch_kwargs))
                try:
                    for item in items:
                        if self.request_delay > 0:
                            await asyncio.sleep(self.request_delay)
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
                            await page.goto(
                                item.url,
                                wait_until="domcontentloaded",
                                timeout=self.request_timeout * 1000,
                            )
                            await asyncio.sleep(1.5)
                            block_reason = await _wait_for_cloudflare(
                                page, item.url, self.logger, max_wait=8
                            )
                            if not block_reason:
                                block_reason = await check_anti_bot(
                                    page, item.url, self.logger
                                )
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
                                    html_path.write_text(
                                        html, encoding="utf-8", errors="replace"
                                    )
                                item.enrichment_source = strategy_name
                                self.logger.debug(
                                    f"[{strategy_name}] {item.title[:50]} ({len(html)} bytes)"
                                )
                                if self.screenshot_enabled:
                                    screenshot_dest = (
                                        image_dir / f"{item.source_id}_screenshot.jpg"
                                    )
                                    try:
                                        await page.screenshot(
                                            path=str(screenshot_dest),
                                            type="jpeg",
                                            quality=85,
                                        )
                                        item.screenshot_image = (
                                            f"images/{item.source_id}_screenshot.jpg"
                                        )
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

        failed_set = set(id(item) for item in failed)
        for item in items:
            if item.enrichment_source != strategy_name and id(item) not in failed_set:
                failed.append(item)
        return failed

    async def capture_screenshot(
        self, url: str, image_dir: Path, source_id: str
    ) -> Optional[str]:
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
                browser = await pw.chromium.launch(**cast(dict, launch_kwargs))
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
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.request_timeout * 1000,
                    )
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

    async def fetch_with_headless(
        self, url: str, screenshot_path: Optional[str] = None
    ) -> Optional[str]:
        """Fetch page using Playwright headless Chrome with stealth anti-detection."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.info(
                "playwright not installed, run: uv add playwright && playwright install chromium"
            )
            return None

        launch_kwargs = {"headless": True, "args": _CHROME_LAUNCH_ARGS}
        if self.browser_executable:
            launch_kwargs["executable_path"] = self.browser_executable

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(**cast(dict, launch_kwargs))
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
                page.on(
                    "console",
                    lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"),
                )

                try:
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.request_timeout * 1000,
                    )
                    await asyncio.sleep(1.5)

                    block_reason = await check_anti_bot(page, url, self.logger)
                    if block_reason:
                        self.logger.debug(f"Headless anti-bot: {block_reason} — {url}")
                        for msg in console_msgs[-5:]:
                            self.logger.debug(f"  console: {msg}")
                        return None

                    if screenshot_path and self.screenshot_enabled:
                        try:
                            await page.screenshot(
                                path=screenshot_path, type="jpeg", quality=85
                            )
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


def _parse_github_url(url: str) -> Optional[tuple]:
    """Extract (owner, repo, path) from a GitHub URL.

    Handles:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/blob/branch/path
      - https://github.com/owner/repo/tree/branch/path
    Returns None if not a GitHub URL.
    """
    parsed = urlparse(url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    # Strip .git suffix
    if repo.endswith(".git"):
        repo = repo[:-4]
    path = None
    if len(parts) >= 4 and parts[2] in ("blob", "tree"):
        path = "/".join(parts[4:])
    return owner, repo, path


async def fetch_github_readme(url: str, logger: logging.Logger) -> Optional[str]:
    """Fetch README content from a GitHub repo via the GitHub API.

    Returns HTML string with the README content, or None on failure.
    """
    parsed = _parse_github_url(url)
    if not parsed:
        return None
    owner, repo, file_path = parsed

    # If URL points to a specific file, fetch that file
    if file_path:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
        headers = {"Accept": "application/vnd.github.v3+json"}
    else:
        # Try README via the accepted HTML media type
        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        headers = {"Accept": "application/vnd.github.v3.html"}

    try:
        async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
            async with session.get(
                api_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"GitHub API {resp.status} for {api_url}")
                    return None
                if file_path:
                    data = await resp.json()
                    content = data.get("content")
                    encoding = data.get("encoding", "base64")
                    if content and encoding == "base64":
                        import base64

                        return base64.b64decode(content).decode(
                            "utf-8", errors="replace"
                        )
                    return None
                # README HTML response
                return await resp.text()
    except Exception as e:
        logger.debug(f"GitHub API failed for {url}: {e}")
        return None


async def _wait_for_cloudflare(
    page, url: str, logger, max_wait: float = 8
) -> Optional[str]:
    """Wait for Cloudflare challenge to auto-resolve. Returns block reason or None."""
    try:
        title = (await page.title()).lower()
    except Exception:
        return None

    is_cf = "just a moment" in title or "checking your browser" in title
    if not is_cf:
        cf_iframe = await page.query_selector(
            'iframe[src*="challenges.cloudflare.com"]'
        )
        is_cf = cf_iframe is not None

    if not is_cf:
        return None

    # Wait for challenge to resolve
    for _ in range(int(max_wait / 0.5)):
        await asyncio.sleep(0.5)
        try:
            title = (await page.title()).lower()
            if "just a moment" not in title and "checking your browser" not in title:
                cf_iframe = await page.query_selector(
                    'iframe[src*="challenges.cloudflare.com"]'
                )
                if not cf_iframe:
                    logger.debug(f"Cloudflare challenge resolved for {url}")
                    return None
        except Exception:
            return "Cloudflare challenge error during wait"

    return "Cloudflare challenge did not resolve"


async def check_anti_bot(page, url: str, logger) -> Optional[str]:
    """Detect anti-bot challenges on the page. Returns reason or None."""
    try:
        title = await page.title()
        url_after = page.url

        # Cloudflare challenge
        if "just a moment" in title.lower() or "checking your browser" in title.lower():
            return "Cloudflare challenge page"
        # Check for common challenge frames
        cf_iframe = await page.query_selector(
            'iframe[src*="challenges.cloudflare.com"]'
        )
        if cf_iframe:
            return "Cloudflare Turnstile/Challenge iframe"

        # Generic CAPTCHA indicators
        captcha = await page.query_selector(
            '[class*="captcha"], [id*="captcha"], .g-recaptcha, .h-captcha'
        )
        if captcha:
            return "CAPTCHA detected"

        # Login/paywall redirects
        parsed_before = urlparse(url)
        parsed_after = urlparse(url_after)
        if parsed_after.hostname and parsed_before.hostname:
            if parsed_after.hostname != parsed_before.hostname:
                if any(
                    kw in parsed_after.hostname
                    for kw in ("login", "auth", "signin", "subscribe", "paywall")
                ):
                    return f"Redirected to {parsed_after.hostname}"

        # JS-rendered empty shell: very few DOM nodes
        node_count = await page.evaluate("document.querySelectorAll('*').length")
        if node_count < 15:
            return f"Near-empty DOM ({node_count} nodes)"

        return None
    except Exception:
        return None
