import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Any
from urllib.parse import urlparse

from openai import OpenAI

from src.core.models import ContentPackage
from src.core.prompts import render_prompt
from src.providers.enricher.page_fetcher import (
    _find_chrome,
    PageFetcher,
    fetch_github_readme,
    _parse_github_url,
)
from src.providers.enricher.image_handler import ImageHandler
from src.providers.enricher.baidu_search import BaiduSearchProvider


class ArticleEnricher:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        enrich_cfg = config.get("enrich", {})
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
        self.use_headed = enrich_cfg.get("headed", False)
        if os.environ.get("HNP_HEADED", "").lower() in ("1", "true", "yes"):
            self.use_headed = True
        self.bing_image_search = enrich_cfg.get("bing_image_search", True)
        self.bing_max_results = enrich_cfg.get("bing_max_results", 3)
        self.bing_max_queries = enrich_cfg.get("bing_max_queries", 2)
        self.screenshot_enabled = enrich_cfg.get("screenshot_enabled", True)
        self.save_fetched_html = enrich_cfg.get("save_fetched_html", True)
        self.headless_batch = enrich_cfg.get("headless_batch", True)
        self.browser_executable = enrich_cfg.get("browser_executable") or _find_chrome()
        if self.browser_executable:
            self.logger.debug(f"Using browser: {self.browser_executable}")

        self.skip_domains = {
            d.lower().lstrip(".") for d in enrich_cfg.get("skip_domains", []) or []
        }

        _target = enrich_cfg.get("image_target_size", [1280, 720])
        _min_size = enrich_cfg.get("image_min_size", [640, 360])

        # Sub-components
        self.fetcher = PageFetcher(
            logger=self.logger,
            retry_count=self.retry_count,
            request_timeout=self.request_timeout,
            request_delay=self.request_delay,
            use_headless=self.use_headless,
            use_headed=self.use_headed,
            screenshot_enabled=self.screenshot_enabled,
            save_fetched_html=self.save_fetched_html,
            browser_executable=self.browser_executable,
        )
        self.image_handler = ImageHandler(
            logger=self.logger,
            max_images=self.max_images,
            max_image_size=self.max_image_size,
            image_target_width=_target[0],
            image_target_height=_target[1],
            image_min_width=_min_size[0],
            image_min_height=_min_size[1],
            bing_image_search=self.bing_image_search,
            bing_max_results=self.bing_max_results,
            bing_max_queries=self.bing_max_queries,
            request_timeout=self.request_timeout,
        )

        # Use llm.fast (lightweight model) for summarization
        fast_cfg = config.get("llm", {}).get("fast", {})
        main_cfg = config.get("llm", {})
        llm_base_url = fast_cfg.get("base_url", main_cfg.get("base_url", ""))
        llm_model = fast_cfg.get("model", main_cfg.get("model", ""))
        llm_max_tokens = self.summary_max_tokens
        llm_temperature = fast_cfg.get("temperature", 0.5)

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

        self.baidu_search = BaiduSearchProvider(config)

        self._enrich_prompt = self._load_prompt("prompts/article_enrich.md")

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

        self._load_image_selection(content, date)

        cache_path = Path(f"data/{date}/enrichment.json")
        if cache_path.exists():
            self._load_from_cache(content, cache_path)

        pages_dir = self._pages_dir(date)
        pages_dir.mkdir(parents=True, exist_ok=True)

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

        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, self._enrich_items(content, date, classified)
                )
                future.result()
        except RuntimeError:
            asyncio.run(self._enrich_items(content, date, classified))

        self._generate_image_selection(content, date)
        self._save_to_cache(content, cache_path)
        self.logger.info("Enrichment complete")
        return content

    async def _enrich_items(self, content: ContentPackage, date: str, classified: dict):
        if classified["full"]:
            await self._phase1_fetch_all(content, date, classified["full"])

        phase2_items = list(classified["phase2_only"])
        for item in classified["full"]:
            if item.enrichment_source not in ("fetch_failed", "skipped", "error"):
                phase2_items.append(item)

        if phase2_items:
            await self._phase2_extract_all(phase2_items, date)

    # ── Item Classification ────────────────────────────────────

    def _classify_items(self, content: ContentPackage, date: str) -> dict:
        pages_dir = self._pages_dir(date)
        result = {"done": [], "phase2_only": [], "full": [], "skipped": []}

        for item in content.items:
            if item.article_text is not None or item.article_summary is not None:
                result["done"].append(item)
                continue

            if not item.url:
                item.enrichment_source = "skipped"
                result["skipped"].append(item)
                continue

            if self.skip_domains:
                host = (urlparse(item.url).hostname or "").lower().lstrip(".")
                if any(host == d or host.endswith("." + d) for d in self.skip_domains):
                    item.enrichment_source = "skipped"
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.editor_angle = None
                    item.dek = None
                    item.key_points = None
                    item.keywords = None
                    item.category = None
                    item.visual_hint = None
                    item.why_it_matters = None
                    item.next_watch = None
                    item.screenshot_image = None
                    result["skipped"].append(item)
                    continue

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
        pages_dir = self._pages_dir(date)
        len(items)

        # Strategy 0: GitHub API (for github.com URLs)
        github_ok, remaining = [], list(items)
        github_items = [item for item in remaining if _parse_github_url(item.url or "")]
        if github_items:
            for item in github_items:
                html = await fetch_github_readme(item.url, self.logger)
                if html and len(html) > 100:
                    html_path = pages_dir / f"{item.source_id}.html"
                    if self.save_fetched_html:
                        html_path.write_text(html, encoding="utf-8", errors="replace")
                    if self._extract_text(html, item.url or ""):
                        item.enrichment_source = "github_api"
                        github_ok.append(item)
                        remaining.remove(item)
                        self.logger.debug(f"[github_api] {item.title[:50]}")
                        continue
                self.logger.debug(
                    f"[github_api] failed, will try aiohttp: {item.title[:50]}"
                )

        # Strategy 1: aiohttp (concurrent)
        aiohttp_failed = []
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _fetch_one(item):
            async with sem:
                return item, await self._phase1_fetch_one_aiohttp(item, pages_dir)

        results = await asyncio.gather(
            *[_fetch_one(item) for item in remaining], return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                self.logger.debug(f"[aiohttp] concurrent fetch error: {r}")
                continue
            item, strategy = r
            if strategy:
                item.enrichment_source = strategy
                self.logger.debug(f"[aiohttp] {item.title[:50]}")
            else:
                aiohttp_failed.append(item)

        aiohttp_ok = len(remaining) - len(aiohttp_failed)
        if remaining:
            self.logger.info(
                f"Phase 1 aiohttp: {aiohttp_ok}/{len(remaining)} ok, "
                f"{len(aiohttp_failed)} → headless"
            )

        # Strategy 2: Headless Chrome
        if aiohttp_failed and self.use_headless:
            headless_failed = await self.fetcher.fetch_browser_batch(
                aiohttp_failed, pages_dir, headless=True, date=date
            )
        else:
            headless_failed = aiohttp_failed

        # Strategy 3: Headed Chrome
        if headless_failed and self.use_headed:
            headed_failed = await self.fetcher.fetch_browser_batch(
                headless_failed, pages_dir, headless=False, date=date
            )
        else:
            headed_failed = headless_failed

        for item in headed_failed:
            item.enrichment_source = "fetch_failed"
            item.article_text = None
            item.article_images = []
            item.article_summary = None
            item.editor_angle = None
            item.dek = None
            item.key_points = None
            item.keywords = None
            item.category = None
            item.visual_hint = None
            item.why_it_matters = None
            item.next_watch = None
            item.screenshot_image = None
            self.logger.info(f"[fetch_failed] {item.title[:50]} ({item.url})")

    async def _phase1_fetch_one_aiohttp(self, item, pages_dir: Path) -> Optional[str]:
        try:
            html = await self.fetcher.fetch_page(item.url)
            if html:
                html_path = pages_dir / f"{item.source_id}.html"
                if self.save_fetched_html:
                    html_path.write_text(html, encoding="utf-8", errors="replace")
                    self.logger.debug(f"HTML saved: {html_path} ({len(html)} bytes)")
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

    # ── Phase 2: Extract from on-disk HTML ─────────────────────

    async def _phase2_extract_all(self, items: list, date: str):
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._phase2_extract_one(item, date, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                self.logger.info(
                    f"Phase 2 extraction failed for item {items[i].source_id}: {r}"
                )

    async def _phase2_extract_one(self, item, date: str, semaphore: asyncio.Semaphore):
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
                cached_image_candidates = self.image_handler.cached_image_candidates(
                    item, image_dir
                )

                article_text = self._extract_text(html, item.url or "")
                if not article_text:
                    item.article_text = None
                    item.article_images = []
                    item.article_summary = None
                    item.editor_angle = None
                    item.dek = None
                    item.key_points = None
                    item.keywords = None
                    item.category = None
                    item.visual_hint = None
                    item.why_it_matters = None
                    item.next_watch = None
                    item.enrichment_source = "extraction_failed"
                    self.logger.debug(f"Phase 2 extraction empty: {item.title[:50]}")
                    return

                image_urls = self.image_handler.extract_images(html, item.url or "")

                page_candidates = []
                if cached_image_candidates:
                    self.logger.debug(
                        f"Reusing {len(cached_image_candidates)} cached image candidates "
                        f"for {item.source_id}"
                    )
                elif image_urls:
                    page_candidates = (
                        await self.image_handler.download_image_candidates(
                            image_urls,
                            image_dir,
                            str(item.source_id),
                            source="page",
                            label="Article image",
                        )
                    )

                bing_candidates = []
                if (
                    not cached_image_candidates
                    and self.bing_image_search
                    and item.title
                ):
                    bing_candidates = await self.image_handler.search_bing_images(
                        item.title,
                        item.url or "",
                        image_dir,
                        str(item.source_id),
                        self.fetcher,
                    )

                screenshot_image = item.screenshot_image
                if not screenshot_image and self.screenshot_enabled:
                    screenshot_filename = f"{item.source_id}_screenshot.jpg"
                    if (image_dir / screenshot_filename).exists():
                        screenshot_image = f"images/{screenshot_filename}"
                    elif item.url:
                        screenshot_image = await self.fetcher.capture_screenshot(
                            item.url, image_dir, str(item.source_id)
                        )
                    item.screenshot_image = screenshot_image

                search_context = ""
                if self.baidu_search.enabled:
                    results = await self.baidu_search.search(item.title or "")
                    search_context = BaiduSearchProvider.format_results(results)

                enrich_result = self._enrich_content(
                    article_text, item.title, search_context
                )
                article_summary = (
                    enrich_result.get("article_summary") if enrich_result else None
                )

                image_candidates = list(cached_image_candidates)
                if not image_candidates:
                    image_candidates.extend(page_candidates)
                    image_candidates.extend(bing_candidates)
                existing_paths = {
                    candidate.get("path")
                    for candidate in image_candidates
                    if candidate.get("path")
                }
                if screenshot_image and screenshot_image not in existing_paths:
                    image_candidates.append(
                        {
                            "path": screenshot_image,
                            "source": "screenshot",
                            "label": "Page screenshot",
                            "rank": len(image_candidates),
                            "width": 1280,
                            "height": 720,
                        }
                    )

                selected_candidate = self.image_handler.choose_auto_image_candidate(
                    image_candidates
                )
                selected_path = (
                    selected_candidate.get("path") if selected_candidate else None
                )
                if selected_path:
                    for candidate in image_candidates:
                        candidate["auto_selected"] = (
                            candidate.get("path") == selected_path
                        )
                    if selected_candidate is not None:
                        selected_candidate["selection_reason"] = (
                            self.image_handler.selection_reason(selected_candidate)
                        )

                item.article_text = article_text[: self.max_text_length]
                item.article_images = self.image_handler.candidate_paths(
                    image_candidates, preferred_path=selected_path
                )
                item.article_summary = article_summary
                if enrich_result:
                    item.editor_angle = enrich_result.get("editor_angle")
                    item.dek = enrich_result.get("dek")
                    item.key_points = enrich_result.get("key_points")
                    item.keywords = enrich_result.get("keywords")
                    item.category = enrich_result.get("category")
                    item.visual_hint = enrich_result.get("visual_hint")
                    item.why_it_matters = enrich_result.get("why_it_matters")
                    item.next_watch = enrich_result.get("next_watch")
                if (
                    not item.enrichment_source
                    or item.enrichment_source == "fetch_failed"
                ):
                    item.enrichment_source = "downloaded_page"

                item.image_candidates = image_candidates

                self.logger.info(
                    f"[{item.enrichment_source}] {item.title[:50]} — "
                    f"{len(article_text)} chars, "
                    f"page={len(page_candidates)} bing={len(bing_candidates)} "
                    f"ss={'Y' if screenshot_image else 'N'}"
                )

            except Exception as e:
                self.logger.info(f"Phase 2 failed for {item.url}: {e}", exc_info=True)
                item.article_text = None
                item.article_images = []
                item.article_summary = None
                item.editor_angle = None
                item.dek = None
                item.key_points = None
                item.keywords = None
                item.category = None
                item.visual_hint = None
                item.why_it_matters = None
                item.next_watch = None
                item.enrichment_source = "error"
                item.enrichment_error = f"{type(e).__name__}: {e}"
                item.screenshot_image = None

    def _extract_text(self, html: str, base_url: str) -> Optional[str]:
        return self.image_handler.extract_text(
            html, base_url, max_text_length=self.max_text_length
        )

    def _enrich_content(
        self, article_text: str, title: str, search_context: str = ""
    ) -> Optional[Dict[str, Any]]:
        if not self._enrich_prompt:
            self.logger.info("Enrich prompt not loaded, skipping LLM enrichment")
            return None

        try:
            prompt = render_prompt(
                self._enrich_prompt,
                title=title,
                article_text=article_text[: self.max_text_length],
                search_context=search_context,
            )

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

            raw = response.choices[0].message.content.strip()
            if not raw or len(raw) < 10:
                return None

            # Strip markdown code fences if present
            text = raw.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [line for line in lines if not line.strip().startswith("```")]
                text = "\n".join(lines)

            result = json.loads(text)
            if not isinstance(result, dict):
                return None
            return result

        except json.JSONDecodeError as e:
            self.logger.info(f"LLM enrichment JSON parse failed for '{title}': {e}")
            return None
        except Exception as e:
            self.logger.info(f"LLM enrichment failed for '{title}': {e}")
            return None

    # ── Image Selection ────────────────────────────────────────

    def _load_image_selection(self, content: ContentPackage, date: str) -> set:
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
                    chosen = entry["selected_image"]
                    existing = [p for p in item.article_images if p != chosen]
                    item.article_images = [chosen] + existing
                    selected.add(str(item.source_id))
                    self.logger.debug(
                        f"Image selection loaded for {item.source_id}: {chosen}"
                    )
            return selected
        except Exception as e:
            self.logger.info(f"Failed to load image selection: {e}")
            return set()

    def _generate_image_selection(self, content: ContentPackage, date: str):
        sel_path = Path(f"data/{date}/image_selection.json")
        existed = sel_path.exists()
        data = {"date": date, "items": {}}
        if existed:
            try:
                with open(sel_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("date", date)
                data.setdefault("items", {})
            except Exception as e:
                self.logger.info(f"Failed to merge image selection, regenerating: {e}")
                data = {"date": date, "items": {}}

        changed = False
        for item in content.items:
            if not item.image_candidates:
                continue
            key = str(item.source_id)
            existing_entry = data["items"].get(key, {})
            candidates = self.image_handler.merge_image_candidates(
                existing_entry.get("candidates", []),
                item.image_candidates,
            )
            selected = existing_entry.get("selected_image")
            if not selected:
                selected_candidate = self.image_handler.choose_auto_image_candidate(
                    candidates
                )
                selected = (
                    selected_candidate.get("path") if selected_candidate else None
                )
                if selected:
                    for candidate in candidates:
                        candidate["auto_selected"] = candidate.get("path") == selected
                    if selected_candidate is not None:
                        selected_candidate["selection_reason"] = (
                            self.image_handler.selection_reason(selected_candidate)
                        )

            new_entry = {
                "title": item.title,
                "url": item.url,
                "candidates": candidates,
                "selected_image": selected,
            }
            if existing_entry != new_entry:
                data["items"][key] = new_entry
                changed = True

        if not data["items"] or (existed and not changed):
            return

        sel_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sel_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        action = "Updated" if existed else "Generated"
        self.logger.info(f"{action} image selection file: {sel_path}")

    # ── Cache ──────────────────────────────────────────────────

    def _save_to_cache(self, content: ContentPackage, cache_path: Path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"date": content.date, "items": {}}
        for item in content.items:
            if item.article_text is not None or item.article_summary is not None:
                data["items"][str(item.source_id)] = {
                    "article_text": item.article_text,
                    "article_images": item.article_images,
                    "article_summary": item.article_summary,
                    "editor_angle": item.editor_angle,
                    "dek": item.dek,
                    "key_points": item.key_points,
                    "keywords": item.keywords,
                    "category": item.category,
                    "visual_hint": item.visual_hint,
                    "why_it_matters": item.why_it_matters,
                    "next_watch": item.next_watch,
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
                    item.editor_angle = cached.get("editor_angle")
                    item.dek = cached.get("dek")
                    item.key_points = cached.get("key_points")
                    item.keywords = cached.get("keywords")
                    item.category = cached.get("category")
                    item.visual_hint = cached.get("visual_hint")
                    item.why_it_matters = cached.get("why_it_matters")
                    item.next_watch = cached.get("next_watch")
                    source = cached.get("enrichment_source") or "legacy"
                    if source == "manual_override":
                        source = "downloaded_page"
                    elif source == "none" and not cached.get("article_text"):
                        source = None
                    item.enrichment_source = source
                    item.enrichment_error = cached.get("enrichment_error")
                    item.logo_image = cached.get("logo_image")
                    item.screenshot_image = cached.get("screenshot_image")
                    item.image_candidates = cached.get("image_candidates", [])
            loaded = sum(
                1
                for item in content.items
                if item.article_text is not None or item.article_summary is not None
            )
            self.logger.debug(f"Loaded {loaded} cached enrichments from {cache_path}")
        except Exception as e:
            self.logger.info(f"Failed to load enrichment cache: {e}")
