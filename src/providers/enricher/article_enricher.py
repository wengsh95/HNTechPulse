import asyncio
import io
import json
import logging
import random
import re
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

def _make_headers() -> Dict[str, str]:
    """Return a copy of base headers with a randomly chosen User-Agent."""
    headers = dict(_BASE_HEADERS)
    headers["User-Agent"] = random.choice(_USER_AGENTS)
    return headers


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
        self.browser_executable = enrich_cfg.get("browser_executable", None)

        # Domains to skip outright — heavy anti-bot, login walls, or
        # sites known to serve nothing useful to scrapers.
        self.skip_domains = {
            d.lower().lstrip(".")
            for d in enrich_cfg.get("skip_domains", []) or []
        }

        _target = enrich_cfg.get("image_target_size", [1280, 720])
        self.image_target_width = _target[0]
        self.image_target_height = _target[1]

        # Proxy
        self.proxy = enrich_cfg.get("proxy", None)

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

        # Load checkpoint
        cache_path = Path(f"data/{date}/enrichment.json")
        if cache_path.exists():
            self._load_from_cache(content, cache_path)

        # Check if all items already enriched
        pending = [
            item for item in content.items
            if item.url and item.article_text is None and item.article_summary is None
        ]
        if not pending:
            self.logger.info("All items already enriched, skipping")
            return content

        self.logger.info(f"Pending enrichment: {len(pending)}/{len(content.items)} items")

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
                    html = await self._fetch_with_headless(item.url)
                    if html:
                        article_text = self._extract_text(html, item.url)
                        image_urls = self._extract_images(html, item.url)
                        if article_text:
                            strategy = "headless"

                # Strategy 3: Give up
                if not article_text:
                    self.logger.info(
                        f"[3/3] All strategies exhausted: {short_title} ({item.url})"
                    )
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.enrichment_source = "none"
                    return

                # Download images
                image_dir = Path(f"data/{date}/images")
                image_dir.mkdir(parents=True, exist_ok=True)
                local_images = []
                if image_urls:
                    local_images = await self._download_images(
                        image_urls, image_dir, str(item.source_id)
                    )

                # LLM summarize
                article_summary = self._summarize(article_text, item.title)

                item.article_text = article_text[:self.max_text_length]
                item.article_images = local_images
                item.article_summary = article_summary
                item.enrichment_source = strategy

                self.logger.info(
                    f"[{strategy}] {short_title} — "
                    f"{len(item.article_text)} chars, {len(local_images)} imgs"
                )

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                self.logger.info(f"Failed to enrich {item.url}: {e}", exc_info=True)
                item.article_text = None
                item.article_images = []
                item.article_summary = None
                item.enrichment_source = "error"
                item.enrichment_error = f"{type(e).__name__}: {e}"

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
            ) as session:
                proxy = self.proxy if self.proxy else None
                async with session.get(
                    url, proxy=proxy, allow_redirects=True, max_redirects=5,
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

    async def _fetch_with_headless(self, url: str) -> Optional[str]:
        """Fetch page using Playwright headless Chrome (real browser fingerprint)."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.info("playwright not installed, run: uv add playwright && playwright install chromium")
            return None

        launch_kwargs = {"headless": True}
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
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.request_timeout * 1000)
                    # Wait a bit for JS-rendered content
                    await asyncio.sleep(1.5)
                    html = await page.content()
                    if html and len(html) > 500:
                        return html
                    return None
                finally:
                    await browser.close()
        except Exception as e:
            self.logger.debug(f"Headless Chrome failed for {url}: {e}")
            return None

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

            return filtered[:self.max_images]
        except Exception as e:
            self.logger.debug(f"Image extraction failed: {e}")
            return []

    async def _download_images(self, urls: List[str], image_dir: Path, source_id: str) -> List[str]:
        local_paths = []
        timeout = aiohttp.ClientTimeout(total=10)
        proxy = self.proxy if self.proxy else None

        async def _fetch_one(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
            """Download one image; return bytes or None. Short reads return None."""
            headers = _make_headers()
            headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            async with session.get(url, headers=headers, proxy=proxy) as resp:
                if resp.status != 200:
                    self.logger.debug(f"Image HTTP {resp.status} for {url}")
                    return None

                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > self.max_image_size:
                    return None

                data = await resp.content.read(self.max_image_size + 1)
                if len(data) > self.max_image_size:
                    return None

                # Guard against CDN-induced short reads: compare against
                # Content-Length and reject if we got notably less. PIL on a
                # severely truncated WebP raises a cryptic "could not create
                # decoder object", so catch it here with a clearer message.
                if cl and len(data) < int(cl) * 0.9:
                    self.logger.debug(
                        f"Short read for {url}: got {len(data)} / {cl} bytes"
                    )
                    return None
                return data

        async with aiohttp.ClientSession(timeout=timeout) as session:
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
                        data = await _fetch_one(session, url)
                    if data is None:
                        continue

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
                    except Exception as e:
                        self.logger.debug(f"Image decode failed for {url}: {e}")

                except Exception as e:
                    self.logger.debug(f"Image download failed for {url}: {e}")

        return local_paths

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
            loaded = sum(1 for item in content.items if item.article_text is not None or item.article_summary is not None)
            self.logger.debug(f"Loaded {loaded} cached enrichments from {cache_path}")
        except Exception as e:
            self.logger.info(f"Failed to load enrichment cache: {e}")
