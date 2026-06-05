import asyncio
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import quote_plus, urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from PIL import Image


class ImageHandler:
    """Handles image extraction, download, search, selection, and caching."""

    def __init__(
        self,
        logger: logging.Logger,
        max_images: int = 3,
        max_image_size: int = 5 * 1024 * 1024,
        image_target_width: int = 1280,
        image_target_height: int = 720,
        image_min_width: int = 640,
        image_min_height: int = 360,
        bing_image_search: bool = True,
        bing_max_results: int = 3,
        bing_max_queries: int = 2,
        request_timeout: int = 15,
    ):
        self.logger = logger
        self.max_images = max_images
        self.max_image_size = max_image_size
        self.image_target_width = image_target_width
        self.image_target_height = image_target_height
        self.image_min_width = image_min_width
        self.image_min_height = image_min_height
        self.bing_image_search = bing_image_search
        self.bing_max_results = bing_max_results
        self.bing_max_queries = bing_max_queries
        self.request_timeout = request_timeout

    # Phrases that indicate session/auth boilerplate, not article content
    _GARBAGE_PATTERNS = (
        "signed in with another tab",
        "signed out in another tab",
        "reload to refresh your session",
        "dismiss alert",
        "checking your browser",
        "just a moment",
        "enable javascript",
    )

    def extract_text(
        self, html: str, base_url: str, max_text_length: int = 8000
    ) -> Optional[str]:
        import trafilatura

        try:
            text = trafilatura.extract(
                html, include_comments=False, include_tables=True, favor_precision=True
            )
            if not text or len(text.strip()) < 200:
                return None
            stripped = text.strip()
            # Reject session/auth boilerplate (e.g. GitHub login notifications)
            lower = stripped.lower()
            if any(pat in lower for pat in self._GARBAGE_PATTERNS):
                self.logger.debug(
                    f"Rejected garbage text ({len(stripped)} chars): {stripped[:80]}..."
                )
                return None
            return stripped[:max_text_length]
        except Exception as e:
            self.logger.debug(f"trafilatura failed: {e}")
            return None

    @staticmethod
    def _best_srcset_url(srcset: str) -> Optional[str]:
        candidates = []
        for part in srcset.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            url = bits[0]
            score = 0
            if len(bits) > 1:
                descriptor = bits[1].lower()
                try:
                    if descriptor.endswith("w"):
                        score = int(descriptor[:-1])
                    elif descriptor.endswith("x"):
                        score = int(float(descriptor[:-1]) * 1000)
                except ValueError:
                    score = 0
            candidates.append((score, url))
        if not candidates:
            return None
        return max(candidates, key=lambda x: x[0])[1]

    def _image_url_from_tag(self, tag) -> Optional[str]:
        for attr in (
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "data-url",
            "poster",
        ):
            value = tag.get(attr)
            if value:
                return value
        srcset = tag.get("srcset") or tag.get("data-srcset")
        if srcset:
            return self._best_srcset_url(srcset)
        return None

    def extract_images(self, html: str, base_url: str) -> List[str]:
        try:
            soup = BeautifulSoup(html, "lxml")
            images = []

            def add_image(raw_url: Optional[str]):
                if not raw_url:
                    return
                img_url = urljoin(base_url, raw_url)
                if img_url not in images:
                    images.append(img_url)

            # 1. og:image
            for og_img in soup.find_all("meta", property="og:image"):
                add_image(cast(Optional[str], og_img.get("content")))

            # 2. twitter:image
            for tw_img in soup.find_all(
                "meta", attrs={"name": re.compile(r"twitter:image", re.I)}
            ):
                add_image(cast(Optional[str], tw_img.get("content")))

            # 3. Article/body images, including lazy-loaded and responsive images
            containers = []
            for selector in ("article", "main", '[role="main"]'):
                found = soup.select_one(selector)
                if found:
                    containers.append(found)
            class_container = soup.find(
                class_=re.compile(r"article|post|content|entry", re.I)
            )
            if class_container:
                containers.append(class_container)
            if not containers:
                containers.append(soup.body or soup)

            seen_container_ids = set()
            for container in containers:
                if id(container) in seen_container_ids:
                    continue
                seen_container_ids.add(id(container))
                for img in container.find_all(
                    ["img", "source", "video"], limit=self.max_images * 4
                ):
                    raw_url = self._image_url_from_tag(img)
                    if not raw_url:
                        continue
                    width = img.get("width", "")
                    height = img.get("height", "")
                    if width and height:
                        try:
                            w = int(str(width))
                            h = int(str(height))
                            if w < 100 or h < 100:
                                continue
                        except (ValueError, TypeError):
                            pass
                    add_image(raw_url)

            # Filter out common non-content patterns
            filtered = []
            skip_patterns = [
                "avatar",
                "logo",
                "icon",
                "badge",
                "pixel",
                "spacer",
                "tracking",
                "analytics",
                "camo.githubusercontent.com",
                # Additional patterns to avoid small/utility images
                "favicon",
                "sprite",
                "emoji",
            ]
            for img_url in images:
                lower = img_url.lower()
                if lower.endswith(".svg") or ".svg?" in lower:
                    self.logger.debug(f"Image filtered out (svg): {img_url}")
                    continue
                # Skip URLs with small dimension patterns like 92x92, 160x160, max-100x100
                if re.search(r"\b\d{2,3}x\d{2,3}\b", lower):
                    self.logger.debug(
                        f"Image filtered out (dimension pattern): {img_url}"
                    )
                    continue
                if not any(p in lower for p in skip_patterns):
                    filtered.append(img_url)
                else:
                    self.logger.debug(
                        f"Image filtered out (matched pattern): {img_url}"
                    )

            result = filtered[: self.max_images]
            self.logger.debug(
                f"Extracted {len(result)} image URLs from {base_url}: {result}"
            )
            return result
        except Exception as e:
            self.logger.debug(f"Image extraction failed: {e}")
            return []

    def candidate_has_suitable_size(self, candidate: Dict[str, Any]) -> bool:
        width = candidate.get("width")
        height = candidate.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            return False
        # Height must not be greater than width (landscape or square preferred)
        if height > width:
            return False
        return width >= self.image_min_width and height >= self.image_min_height

    def choose_auto_image_candidate(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        for candidate in candidates:
            if candidate.get("source") == "page" and self.candidate_has_suitable_size(
                candidate
            ):
                return candidate
        for candidate in candidates:
            if candidate.get("source") == "screenshot" and candidate.get("path"):
                return candidate
        for candidate in candidates:
            if candidate.get("source") == "bing" and self.candidate_has_suitable_size(
                candidate
            ):
                return candidate

        for source in ("page", "bing", "screenshot"):
            for candidate in candidates:
                if candidate.get("source") == source and candidate.get("path"):
                    return candidate
        return None

    def selection_reason(self, candidate: Dict[str, Any]) -> str:
        source = candidate.get("source")
        if source == "page":
            return (
                "article_image_suitable"
                if self.candidate_has_suitable_size(candidate)
                else "article_image_fallback"
            )
        if source == "screenshot":
            return "page_screenshot"
        if source == "bing":
            return (
                "bing_image_suitable"
                if self.candidate_has_suitable_size(candidate)
                else "bing_image_fallback"
            )
        return "fallback"

    @staticmethod
    def candidate_paths(
        candidates: List[Dict[str, Any]], preferred_path: Optional[str] = None
    ) -> List[str]:
        paths = []
        seen = set()
        if preferred_path:
            paths.append(preferred_path)
            seen.add(preferred_path)
        for candidate in candidates:
            path = candidate.get("path")
            if path and path not in seen:
                paths.append(path)
                seen.add(path)
        return paths

    @staticmethod
    def image_cache_path_exists(image_dir: Path, path: Optional[str]) -> bool:
        if not path:
            return False
        p = Path(path)
        if p.is_absolute():
            return p.exists()
        if len(p.parts) >= 2 and p.parts[0] == "images":
            return (image_dir / p.name).exists()
        return (image_dir / p).exists()

    def cached_image_candidates(self, item, image_dir: Path) -> List[Dict[str, Any]]:
        """Return cached image candidates whose local files still exist."""
        candidates: List[Dict[str, Any]] = []
        seen = set()

        for candidate in item.image_candidates or []:
            path = candidate.get("path")
            if (
                path
                and path not in seen
                and self.image_cache_path_exists(image_dir, path)
            ):
                candidates.append(dict(candidate))
                seen.add(path)

        for rank, path in enumerate(item.article_images or []):
            if path in seen or not self.image_cache_path_exists(image_dir, path):
                continue
            candidates.append(
                {
                    "path": path,
                    "source": "cached",
                    "label": "Cached image",
                    "rank": rank,
                }
            )
            seen.add(path)

        screenshot_image = item.screenshot_image
        if (
            screenshot_image
            and screenshot_image not in seen
            and self.image_cache_path_exists(image_dir, screenshot_image)
        ):
            candidates.append(
                {
                    "path": screenshot_image,
                    "source": "screenshot",
                    "label": "Page screenshot",
                    "rank": len(candidates),
                    "width": 1280,
                    "height": 720,
                }
            )

        return candidates

    async def download_image_candidates(
        self,
        urls: List[str],
        image_dir: Path,
        source_id: str,
        source: str,
        label: str,
    ) -> List[Dict[str, Any]]:
        from src.providers.enricher.page_fetcher import _make_headers

        candidates: List[Dict[str, Any]] = []
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)

        async def _fetch_one(
            session: aiohttp.ClientSession, url: str
        ) -> Optional[bytes]:
            headers = _make_headers()
            headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"

            # HEAD precheck to avoid downloading oversized images
            try:
                async with session.head(
                    url, headers=headers, allow_redirects=True
                ) as head_resp:
                    if head_resp.status == 200:
                        cl = head_resp.headers.get("Content-Length")
                        if cl and int(cl) > self.max_image_size:
                            self.logger.debug(
                                f"Image precheck too large ({cl} bytes) for {url}"
                            )
                            return None
            except Exception:
                pass  # HEAD not supported, fall through to GET

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
                    self.logger.warning(
                        f"Image read too large ({len(data)} bytes) for {url}"
                    )
                    return None

                # Skip short-read check for compressed responses:
                # Content-Length reflects compressed size, not decompressed size.
                ce = resp.headers.get("Content-Encoding", "")
                if cl and not ce and len(data) < int(cl) * 0.9:
                    self.logger.warning(
                        f"Short read for {url}: got {len(data)} / {cl} bytes"
                    )
                    return None
                return data

        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            # Parallelize network downloads
            async def _download_one(idx: int, url: str):
                filename = f"{source_id}_{idx}.jpg"
                dest = image_dir / filename
                if dest.exists():
                    return idx, url, dest, None, True
                data = await _fetch_one(session, url)
                if data is None:
                    self.logger.debug(f"Image fetch retry: {url}")
                    data = await _fetch_one(session, url)
                if data is None:
                    self.logger.warning(f"Image fetch failed after retry: {url}")
                    return idx, url, dest, None, False
                return idx, url, dest, data, False

            results = await asyncio.gather(
                *[_download_one(idx, url) for idx, url in enumerate(urls)],
                return_exceptions=True,
            )

            # Process downloads in order (sequential PIL processing)
            for r in results:
                if isinstance(r, Exception):
                    self.logger.debug(f"Image download error: {r}")
                    continue
                idx, url, dest, data, was_cached = r
                if was_cached:
                    candidates.append(
                        {
                            "path": f"images/{dest.name}",
                            "source": source,
                            "label": label,
                            "origin_url": url,
                            "rank": idx,
                        }
                    )
                    continue
                if data is None:
                    continue

                self.logger.debug(f"Image fetched {len(data)} bytes from {url}")
                try:
                    img: Any = Image.open(io.BytesIO(data))
                    img = img.convert("RGB")

                    # Skip portrait images (height > width)
                    if img.height > img.width:
                        self.logger.debug(
                            f"Image skipped (portrait: {img.width}x{img.height}): {url}"
                        )
                        continue

                    if img.width < 200 or img.height < 200:
                        self.logger.debug(
                            f"Image skipped (too small: {img.width}x{img.height}): {url}"
                        )
                        continue

                    if (
                        img.width > self.image_target_width
                        or img.height > self.image_target_height
                    ):
                        img.thumbnail(
                            (self.image_target_width, self.image_target_height),
                            Image.Resampling.LANCZOS,
                        )

                    img.save(dest, "JPEG", quality=85)
                    candidates.append(
                        {
                            "path": f"images/{dest.name}",
                            "source": source,
                            "label": label,
                            "origin_url": url,
                            "rank": idx,
                            "width": img.width,
                            "height": img.height,
                        }
                    )
                    self.logger.debug(f"Image saved: {dest} ({img.width}x{img.height})")
                except Exception as e:
                    self.logger.warning(f"Image decode failed for {url}: {e}")

        return candidates

    async def search_bing_images(
        self, title: str, url: str, image_dir: Path, source_id: str, fetcher
    ) -> List[Dict[str, Any]]:
        """Search Bing Images for article title, download top results."""
        domain = urlparse(url).hostname or ""
        queries = []
        if domain:
            queries.append(f"{title} site:{domain}".strip())
        queries.append(title.strip())

        try:
            image_urls = []
            used_queries = []
            for query in queries[: max(1, self.bing_max_queries)]:
                if not query:
                    continue
                search_url = (
                    f"https://www.bing.com/images/search?q={quote_plus(query)}&first=1"
                )
                html = await fetcher.fetch_with_headless(search_url)
                if not html:
                    html = await fetcher.fetch_page(search_url)
                if not html:
                    continue

                for img_url in self._extract_bing_image_urls(html):
                    if img_url not in image_urls:
                        image_urls.append(img_url)
                        used_queries.append(query)
                    if len(image_urls) >= self.bing_max_results:
                        break
                if len(image_urls) >= self.bing_max_results:
                    break

            candidates = await self.download_image_candidates(
                image_urls[: self.bing_max_results],
                image_dir,
                f"{source_id}_bing",
                source="bing",
                label="Bing result",
            )
            for candidate in candidates:
                idx = candidate.get("rank", 0)
                if isinstance(idx, int) and idx < len(used_queries):
                    candidate["query"] = used_queries[idx]
            return candidates
        except Exception as e:
            self.logger.info(f"Bing image search failed for '{title}': {e}")
            return []

    def _extract_bing_image_urls(self, html: str) -> List[str]:
        """Extract image URLs from Bing Images search results HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")
            urls = []
            for a_tag in soup.find_all(
                "a", class_="iusc", limit=self.bing_max_results * 2
            ):
                m_attr = a_tag.get("m")
                if isinstance(m_attr, str):
                    try:
                        m_data: dict = json.loads(m_attr)
                        img_url = m_data.get("murl") or m_data.get("turl")
                        if img_url and img_url not in urls:
                            urls.append(img_url)
                    except json.JSONDecodeError:
                        continue
            if not urls:
                for img in soup.find_all("img", limit=self.bing_max_results * 3):
                    src = img.get("src") or ""
                    if "bing.com/th" in src and src not in urls:
                        urls.append(src)
            return urls[: self.bing_max_results]
        except Exception as e:
            self.logger.debug(f"Bing image URL extraction failed: {e}")
            return []

    @staticmethod
    def merge_image_candidates(
        existing: List[Dict[str, Any]],
        new: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged = []
        seen = set()
        for candidate in list(existing or []) + list(new or []):
            path = candidate.get("path")
            if not path or path in seen:
                continue
            merged.append(candidate)
            seen.add(path)
        return merged
