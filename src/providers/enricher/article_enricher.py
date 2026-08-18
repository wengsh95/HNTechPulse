import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Any, cast
from urllib.parse import urlparse

from src.core.interfaces import LLMProvider
from src.core.models import ContentPackage
from src.core.prompts import render_prompt
from src.providers.enricher.page_fetcher import (
    _find_chrome,
    PageFetcher,
    fetch_github_readme,
    _parse_github_url,
)
from src.providers.enricher.image_handler import ImageHandler
from src.providers.enricher.relevance import assess_article_relevance
from src.pipeline.paths import (
    media_images_dir,
    pipeline_path,
    raw_downloaded_pages_dir,
)
from src.utils.async_helper import run_async


class ArticleEnricher:
    LOW_VALUE_KEYWORDS = {
        "AI",
        "人工智能",
        "技术",
        "工具",
        "平台",
        "系统",
        "应用",
        "创新",
        "趋势",
        "生态",
        "开发者",
        "软件",
        "服务",
        "产品",
        "数据",
        "模型",
        "代码",
        "开源",
    }

    def __init__(
        self,
        llm_provider: LLMProvider,
        config: dict,
        debug: bool = False,
        agent_mode: bool = False,
    ):
        self.llm_provider = llm_provider
        self.llm_client = llm_provider.llm_client
        self.config = config
        self.debug = debug
        # In managed agent runs the current agent is the image editor.  The
        # pipeline may collect candidates, but it must not silently decide
        # which image is semantically correct.
        self.agent_mode = agent_mode
        self.pending_image_selections: list[dict[str, Any]] = []
        enrich_cfg = config.get("enrich", {})
        self.logger = logging.getLogger("hn_techpulse.enricher")

        self.enabled = enrich_cfg.get("enabled", False)
        self.max_text_length = enrich_cfg.get("max_text_length", 8000)
        self.max_images = enrich_cfg.get("max_images", 3)
        self.max_image_size = enrich_cfg.get("max_image_size", 5 * 1024 * 1024)
        self.request_timeout = enrich_cfg.get("request_timeout", 15)
        self.max_concurrent = enrich_cfg.get("max_concurrent", 10)
        self.summary_max_tokens = enrich_cfg.get("summary_max_tokens", 512)
        self.retry_count = enrich_cfg.get("retry_count", 3)
        self.request_delay = enrich_cfg.get("request_delay", 0.5)
        self.use_headless = enrich_cfg.get("headless", True)
        self.use_headed = enrich_cfg.get("headed", False)
        if os.environ.get("HNP_HEADED", "").lower() in ("1", "true", "yes"):
            self.use_headed = True
        self.bing_image_search = enrich_cfg.get("bing_image_search", True)
        self.bing_max_results = enrich_cfg.get("bing_max_results", 5)
        self.bing_max_queries = enrich_cfg.get("bing_max_queries", 4)
        self.bing_entity_search = enrich_cfg.get("bing_entity_search", True)
        self.bing_entity_all_stories = enrich_cfg.get("bing_entity_all_stories", False)
        self.bing_logo_fallback = enrich_cfg.get("bing_logo_fallback", True)
        self.screenshot_enabled = enrich_cfg.get("screenshot_enabled", True)
        self.save_fetched_html = enrich_cfg.get("save_fetched_html", True)
        self.headless_batch = enrich_cfg.get("headless_batch", True)
        self.browser_executable = enrich_cfg.get("browser_executable") or _find_chrome()
        if self.browser_executable:
            self.logger.debug(f"Using browser: {self.browser_executable}")

        self.skip_domains = {
            d.lower().lstrip(".") for d in enrich_cfg.get("skip_domains", []) or []
        }

        self.pdf_enabled = enrich_cfg.get("pdf_enabled", True)
        self.pdf_max_size = enrich_cfg.get("pdf_max_size", 20 * 1024 * 1024)
        self.pdf_extract_images = enrich_cfg.get("pdf_extract_images", True)

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

        self._enrich_prompt = self._load_prompt("prompts/article_enrich.md")
        self._image_entities_prompt = self._load_prompt("prompts/image_entities.md")

    @staticmethod
    def _load_prompt(path: str) -> str:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return ""

    def _pages_dir(self, date: str) -> Path:
        return raw_downloaded_pages_dir(date)

    def enrich(self, content: ContentPackage, date: str) -> ContentPackage:
        if not self.enabled:
            self.logger.info("Article enrichment disabled, skipping")
            return content

        self.logger.info(f"Enriching {len(content.items)} items...")
        self.pending_image_selections = []

        self._load_image_selection(content, date)

        cache_path = pipeline_path(date, "enrichment.json")
        if cache_path.exists():
            self._load_from_cache(content, cache_path)
        self._invalidate_cached_mismatches(content)

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

        run_async(self._enrich_items(content, date, classified))

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

    @staticmethod
    def _clear_enrichment(item, *, source: str, error: str) -> None:
        item.article_text = None
        item.article_images = []
        item.article_summary = None
        item.editor_angle = None
        item.dek = None
        item.key_points = None
        item.keywords = None
        item.category = None
        item.why_it_matters = None
        item.screenshot_image = None
        item.enrichment_source = source
        item.enrichment_error = error

    def _mark_content_mismatch(self, item, article_text: str) -> bool:
        relevance = assess_article_relevance(
            item.title,
            article_text,
            url=item.url,
        )
        item.article_relevance_score = relevance.score
        if relevance.accepted:
            return True
        self._clear_enrichment(
            item,
            source="content_mismatch",
            error=(
                f"{relevance.reason}; title_tokens={list(relevance.title_tokens)}; "
                f"overlap={list(relevance.overlapping_tokens)}"
            ),
        )
        self.logger.warning(
            f"[content_mismatch] {item.title[:70]} — "
            f"score={relevance.score:.3f} reason={relevance.reason}"
        )
        return False

    def _invalidate_cached_mismatches(self, content: ContentPackage) -> None:
        for item in content.items:
            if not item.url or not item.article_text:
                continue
            if not self._mark_content_mismatch(item, item.article_text):
                continue

    # ── Item Classification ────────────────────────────────────

    def _classify_items(self, content: ContentPackage, date: str) -> dict:
        pages_dir = self._pages_dir(date)
        result: Dict[str, list] = {
            "done": [],
            "phase2_only": [],
            "full": [],
            "skipped": [],
        }

        for item in content.items:
            if item.enrichment_source == "content_mismatch":
                result["skipped"].append(item)
                continue
            if item.article_text is not None or item.article_summary is not None:
                result["done"].append(item)
                continue

            if not item.url:
                # HN self-posts (Ask HN / Show HN) have no external URL. If the
                # fetcher piped HNStory.text through as self_post_text, route
                # it to phase 2 so the LLM can still extract editor_angle / dek /
                # key_points from the body the OP wrote.
                if item.self_post_text:
                    result["phase2_only"].append(item)
                    continue
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
                    item.why_it_matters = None
                    item.screenshot_image = None
                    result["skipped"].append(item)
                    continue

            html_path = pages_dir / f"{item.source_id}.html"
            pdf_path = pages_dir / f"{item.source_id}.pdf"
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
            elif pdf_path.exists():
                item.enrichment_source = "pdf"
                result["phase2_only"].append(item)
            else:
                result["full"].append(item)

        return result

    # ── Phase 1: Fetch HTML to disk ────────────────────────────

    async def _phase1_fetch_all(self, content: ContentPackage, date: str, items: list):
        pages_dir = self._pages_dir(date)

        # Strategy 0: GitHub API (for github.com URLs)
        github_ok, remaining = [], list(items)
        github_fallback = []  # GitHub API failed → skip aiohttp, go straight to headless
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
                # GitHub pages are JS-rendered — aiohttp can't extract README,
                # skip straight to headless browser
                remaining.remove(item)
                github_fallback.append(item)
                self.logger.debug(
                    f"[github_api] failed, will try headless: {item.title[:50]}"
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
            if not isinstance(r, tuple):
                continue
            item, strategy = r
            if strategy:
                item.enrichment_source = strategy
                self.logger.debug(f"[aiohttp] {item.title[:50]}")
            else:
                aiohttp_failed.append(item)

        aiohttp_ok = len(remaining) - len(aiohttp_failed)
        # GitHub API failures skip aiohttp (JS-rendered pages), go straight to headless
        aiohttp_failed.extend(github_fallback)
        if remaining:
            self.logger.info(
                f"Phase 1 aiohttp: {aiohttp_ok}/{len(remaining)} ok, "
                f"{len(aiohttp_failed)} → headless"
            )

        # Strategy 2: Headless Chrome
        if aiohttp_failed and self.use_headless:
            self.logger.info(
                f"Phase 1 headless: starting batch of {len(aiohttp_failed)} items"
            )
            headless_failed = await self.fetcher.fetch_browser_batch(
                aiohttp_failed, pages_dir, headless=True, date=date
            )
            self.logger.info(
                f"Phase 1 headless: {len(aiohttp_failed) - len(headless_failed)}/"
                f"{len(aiohttp_failed)} ok, {len(headless_failed)} → headed"
            )
        else:
            headless_failed = aiohttp_failed

        # Strategy 3: Headed Chrome
        if headless_failed and self.use_headed:
            self.logger.info(
                f"Phase 1 headed: starting batch of {len(headless_failed)} items"
            )
            headed_failed = await self.fetcher.fetch_browser_batch(
                headless_failed, pages_dir, headless=False, date=date
            )
            self.logger.info(
                f"Phase 1 headed: {len(headless_failed) - len(headed_failed)}/"
                f"{len(headless_failed)} ok, {len(headed_failed)} unrecovered"
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
            item.why_it_matters = None
            item.screenshot_image = None
            self.logger.info(f"[fetch_failed] {item.title[:50]} ({item.url})")

    async def _phase1_fetch_one_aiohttp(self, item, pages_dir: Path) -> Optional[str]:
        try:
            html = await self.fetcher.fetch_page(item.url)
            if html == "__PDF__":
                if not self.pdf_enabled:
                    self.logger.debug(
                        f"PDF support disabled, skipping: {item.title[:50]}"
                    )
                    return None
                pdf_data = await self.fetcher.fetch_pdf(
                    item.url, max_size=self.pdf_max_size
                )
                if pdf_data:
                    pdf_path = pages_dir / f"{item.source_id}.pdf"
                    if self.save_fetched_html:
                        pdf_path.write_bytes(pdf_data)
                        self.logger.debug(
                            f"PDF saved: {pdf_path} ({len(pdf_data)} bytes)"
                        )
                    return "pdf"
                self.logger.debug(f"[aiohttp] PDF download failed: {item.title[:50]}")
                return None
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

    async def _enrich_self_post(self, item) -> None:
        """Run LLM extraction for an HN self-post (no external URL).

        Uses the body text captured from HNStory.text. Skips page/screenshot
        image fetching (no URL to capture from) and reuses the same
        _enrich_content() prompt as the HTML/PDF paths so the output schema
        matches the rest of the pipeline.
        """
        article_text = (item.self_post_text or "").strip()
        if not article_text:
            item.enrichment_source = "skipped"
            self.logger.debug(f"[self_post] empty body: {item.title[:50]}")
            return

        try:
            enrich_result = self._enrich_content(article_text, item.title)
        except Exception as e:
            self.logger.warning(
                f"[self_post] LLM extraction failed: {item.title[:50]}: {e}"
            )
            item.enrichment_source = "extraction_failed"
            return

        item.article_text = article_text[: self.max_text_length]
        if enrich_result:
            item.article_summary = enrich_result.get("article_summary")
            item.editor_angle = enrich_result.get("editor_angle")
            item.dek = enrich_result.get("dek")
            item.key_points = enrich_result.get("key_points")
            item.category = enrich_result.get("category")
            item.why_it_matters = enrich_result.get("why_it_matters")
            item.keywords = self._normalize_keywords(
                enrich_result.get("keywords"),
                category=item.category,
                fallback_values=[
                    item.editor_angle,
                    item.dek,
                    item.why_it_matters,
                    item.title,
                ],
            )
        item.enrichment_source = "self_post"
        self.logger.info(f"[self_post] {item.title[:50]} — {len(article_text)} chars")

    async def _phase2_extract_all(self, items: list, date: str):
        self.logger.info(f"Phase 2: starting extraction for {len(items)} items")
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [self._phase2_extract_one(item, date, semaphore) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                self.logger.info(
                    f"Phase 2 extraction failed for item {items[i].source_id}: {r}"
                )
        self.logger.info(f"Phase 2: done ({len(items)} items processed)")

    async def _phase2_extract_one(self, item, date: str, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                # ── Self-post path: HN body text (no HTML/PDF on disk) ──
                if item.self_post_text and not item.url and not item.article_text:
                    await self._enrich_self_post(item)
                    return

                pages_dir = self._pages_dir(date)
                html_path = pages_dir / f"{item.source_id}.html"
                pdf_path = pages_dir / f"{item.source_id}.pdf"

                if not html_path.exists() and not pdf_path.exists():
                    item.enrichment_source = "fetch_failed"
                    return

                # ── PDF path ──
                if pdf_path.exists() and not html_path.exists():
                    image_dir = media_images_dir(date)
                    image_dir.mkdir(parents=True, exist_ok=True)

                    article_text = self._extract_pdf_text(pdf_path)
                    if not article_text:
                        item.article_text = None
                        item.article_images = []
                        item.article_summary = None
                        item.editor_angle = None
                        item.dek = None
                        item.key_points = None
                        item.keywords = None
                        item.category = None
                        item.why_it_matters = None
                        item.enrichment_source = "extraction_failed"
                        self.logger.debug(f"PDF extraction empty: {item.title[:50]}")
                        return

                    if not self._mark_content_mismatch(item, article_text):
                        return

                    pdf_image_candidates = self._extract_pdf_images(
                        pdf_path, image_dir, str(item.source_id)
                    )

                    enrich_result = self._enrich_content(article_text, item.title)
                    article_summary = (
                        enrich_result.get("article_summary") if enrich_result else None
                    )

                    image_candidates = list(pdf_image_candidates)
                    setattr(item, "_content_date", date)
                    selected_candidate = self._select_image_candidate(
                        item, image_candidates, article_summary=article_summary
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
                        item.category = enrich_result.get("category")
                        item.why_it_matters = enrich_result.get("why_it_matters")
                        item.keywords = self._normalize_keywords(
                            enrich_result.get("keywords"),
                            category=item.category,
                            fallback_values=[
                                item.editor_angle,
                                item.dek,
                                item.why_it_matters,
                                item.title,
                            ],
                        )
                    item.enrichment_source = "pdf"
                    item.image_candidates = image_candidates

                    self.logger.info(
                        f"[pdf] {item.title[:50]} — "
                        f"{len(article_text)} chars, "
                        f"images={len(pdf_image_candidates)}"
                    )
                    return

                # ── HTML path ──

                html = html_path.read_text(encoding="utf-8", errors="replace")
                image_dir = media_images_dir(date)
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
                    item.why_it_matters = None
                    item.enrichment_source = "extraction_failed"
                    self.logger.debug(f"Phase 2 extraction empty: {item.title[:50]}")
                    return

                if not self._mark_content_mismatch(item, article_text):
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
                entity_queries: list[str] = []
                # Skip Bing if page already has suitable images (≥640x360)
                has_suitable_page_images = any(
                    self.image_handler.candidate_has_suitable_size(c)
                    for c in page_candidates
                )
                want_bing = (
                    not cached_image_candidates
                    and self.bing_image_search
                    and item.title
                    and (not has_suitable_page_images or self.bing_entity_all_stories)
                )
                if want_bing:
                    entity_queries = (
                        self._extract_image_entities(item)
                        if self.bing_entity_search
                        else []
                    )
                    bing_candidates = await self.image_handler.search_bing_images(
                        item.title,
                        item.url or "",
                        image_dir,
                        str(item.source_id),
                        self.fetcher,
                        entity_queries=entity_queries,
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

                enrich_result = self._enrich_content(article_text, item.title)
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

                # Last-resort visual coverage: if the article supplied no
                # usable image and the page screenshot was unavailable, search
                # for the relevant entity/concept logo.  This is still only a
                # candidate; agent mode will ask the current agent to inspect
                # it before accepting it as the final image.
                if (
                    not image_candidates
                    and self.bing_image_search
                    and self.bing_logo_fallback
                ):
                    logo_queries = self._logo_image_queries(item, entity_queries)
                    if logo_queries:
                        logo_candidates = await self.image_handler.search_bing_images(
                            item.title,
                            item.url or "",
                            image_dir,
                            str(item.source_id),
                            self.fetcher,
                            entity_queries=logo_queries,
                            label="Bing logo fallback",
                        )
                        for candidate in logo_candidates:
                            candidate["fallback_kind"] = "logo"
                        image_candidates.extend(logo_candidates)

                setattr(item, "_content_date", date)
                selected_candidate = self._select_image_candidate(
                    item, image_candidates, article_summary=article_summary
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
                    item.category = enrich_result.get("category")
                    item.why_it_matters = enrich_result.get("why_it_matters")
                    item.keywords = self._normalize_keywords(
                        enrich_result.get("keywords"),
                        category=item.category,
                        fallback_values=[
                            item.editor_angle,
                            item.dek,
                            item.why_it_matters,
                            item.title,
                        ],
                    )
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
                item.enrichment_source = "error"
                item.enrichment_error = f"{type(e).__name__}: {e}"
                item.screenshot_image = None

    def _extract_text(self, html: str, base_url: str) -> Optional[str]:
        return self.image_handler.extract_text(
            html, base_url, max_text_length=self.max_text_length
        )

    def _extract_pdf_text(self, pdf_path: Path) -> Optional[str]:
        """Extract text from a PDF file using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            self.logger.warning("pdfplumber not installed, cannot extract PDF text")
            return None

        try:
            text_parts = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            full_text = "\n\n".join(text_parts).strip()
            if full_text and len(full_text) > 100:
                return full_text[: self.max_text_length]
            return None
        except Exception as e:
            self.logger.debug(f"PDF text extraction failed for {pdf_path}: {e}")
            return None

    def _extract_pdf_images(
        self, pdf_path: Path, image_dir: Path, source_id: str
    ) -> list[dict]:
        """Extract images from a PDF file using pdfplumber."""
        if not self.pdf_extract_images:
            return []
        try:
            import pdfplumber
        except ImportError:
            return []

        candidates: list = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    images = page.images
                    if not images:
                        continue
                    for img_idx, img in enumerate(images[:3]):
                        try:
                            cropped = page.within_bbox(
                                (img["x0"], img["top"], img["x1"], img["bottom"])
                            ).to_image(resolution=150)
                            filename = f"{source_id}_pdf_p{page_idx}_{img_idx}.jpg"
                            dest = image_dir / filename
                            cropped.save(dest, format="JPEG")
                            candidates.append(
                                {
                                    "path": f"images/{filename}",
                                    "source": "pdf",
                                    "label": "PDF embedded image",
                                    "rank": len(candidates),
                                }
                            )
                        except Exception as e:
                            self.logger.debug(f"PDF image crop failed: {e}")
                    if len(candidates) >= self.max_images:
                        break
        except Exception as e:
            self.logger.debug(f"PDF image extraction failed for {pdf_path}: {e}")
        return candidates

    def _extract_image_entities(self, item: Any) -> list[str]:
        """Ask the fast model for 1-3 image-search-friendly entity queries.

        Widens the Bing candidate pool with brand/product/landmark terms (e.g.
        "OpenAI logo", "US Capitol building") that a title-only query misses.
        Returns [] on any failure — Bing then falls back to title queries.
        """
        if not self._image_entities_prompt or not item.title:
            return []

        prompt = render_prompt(
            self._image_entities_prompt,
            title=item.title or "",
            title_cn=item.title_cn or "",
            editor_angle=item.editor_angle or "",
            keywords=json.dumps(item.keywords or [], ensure_ascii=False),
        )
        if "<!-- SYSTEM_CUT -->" in prompt:
            system_msg, user_msg = (
                p.strip() for p in prompt.split("<!-- SYSTEM_CUT -->", 1)
            )
        else:
            system_msg = "你是图片检索策划。"
            user_msg = prompt
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        def _validate(parsed: Any) -> None:
            if not isinstance(parsed, dict) or not isinstance(
                parsed.get("queries"), list
            ):
                raise ValueError("image entities result missing 'queries' list")

        try:
            response_text = self.llm_client.call_llm_with_json_retry(
                messages=messages,
                label=f"image_entities_{(item.title or '')[:30]}",
                max_tokens=256,
                model=self.llm_client.fast_model,
                temperature=self.llm_client.fast_temperature,
                validator=_validate,
            )
            parsed = self.llm_client.extract_json(response_text)
        except Exception as e:
            self.logger.info(f"Image entity extraction failed for '{item.title}': {e}")
            return []

        queries = [
            str(q).strip() for q in (parsed.get("queries") or []) if str(q).strip()
        ]
        return queries[:3]

    @staticmethod
    def _logo_image_queries(item: Any, entity_queries: list[str]) -> list[str]:
        queries: list[str] = []
        for value in [
            *entity_queries,
            *(item.keywords or []),
            item.category or "",
            item.title or "",
        ]:
            text = str(value).strip()
            if not text:
                continue
            query = f"{text} logo"
            if query not in queries:
                queries.append(query)
            if len(queries) >= 3:
                break
        return queries

    def _enrich_content(
        self, article_text: str, title: str
    ) -> Optional[Dict[str, Any]]:
        if not self._enrich_prompt:
            self.logger.info("Enrich prompt not loaded, skipping LLM enrichment")
            return None

        prompt = render_prompt(
            self._enrich_prompt,
            title=title,
            article_text=article_text[: self.max_text_length],
        )

        if "<!-- SYSTEM_CUT -->" in prompt:
            parts = prompt.split("<!-- SYSTEM_CUT -->", 1)
            system_msg = parts[0].strip()
            user_msg = parts[1].strip()
        else:
            system_msg = "你是一位技术内容分析师。"
            user_msg = prompt

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        def _validate(parsed: Any) -> None:
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"enrichment result is not a JSON object (got {type(parsed).__name__})"
                )
            # Sanity: editor_angle and key_points are the load-bearing fields
            # consumed by write_script. If the model hallucinates a valid-looking
            # JSON object without them, retry rather than silently storing
            # None and crashing downstream.
            if not parsed.get("editor_angle") or not parsed.get("key_points"):
                missing = [
                    f for f in ("editor_angle", "key_points") if not parsed.get(f)
                ]
                raise ValueError(
                    f"enrichment result missing required fields: {missing}"
                )

        for attempt in range(self.retry_count):
            try:
                response_text = self.llm_client.call_llm_with_json_retry(
                    messages=messages,
                    label=f"enrich_{title[:30]}",
                    max_tokens=self.summary_max_tokens,
                    model=self.llm_client.fast_model,
                    temperature=self.llm_client.fast_temperature,
                    validator=_validate,
                )
                return self.llm_client.extract_json(response_text)
            except Exception as e:
                self.logger.info(
                    f"LLM enrichment failed for '{title}' "
                    f"(attempt {attempt + 1}/{self.retry_count}): {e}"
                )

        self.logger.info(
            f"LLM enrichment exhausted {self.retry_count} retries for '{title}'"
        )
        return None

    @classmethod
    def _normalize_keywords(
        cls,
        keywords: Any,
        category: Optional[str] = None,
        fallback_values: Optional[list[Any]] = None,
    ) -> list[str]:
        """Keep LLM keywords useful as compact video labels and highlight anchors."""
        normalized: list[str] = []
        seen: set[str] = set()
        category_key = cls._keyword_key(category)

        def add(value: Any) -> None:
            if value is None or len(normalized) >= 3:
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    add(item)
                return

            text = str(value).strip()
            if not text:
                return
            text = text.strip(" #，,、。；;：:|/\\()（）[]【】{}<>《》\"'`")
            text = " ".join(text.split())
            if not text:
                return

            key = cls._keyword_key(text)
            if not key or key in seen:
                return
            if category_key and key == category_key:
                return
            if text in cls.LOW_VALUE_KEYWORDS:
                return
            if len(text) == 1:
                return

            seen.add(key)
            normalized.append(text)

        add(keywords)
        for value in fallback_values or []:
            add(value)
            if len(normalized) >= 3:
                break

        return normalized[:3]

    @staticmethod
    def _keyword_key(value: Any) -> str:
        if value is None:
            return ""
        return "".join(str(value).lower().split())

    # ── Image Selection ────────────────────────────────────────

    def _select_image_candidate(
        self,
        item,
        candidates: list[Dict[str, Any]],
        article_summary: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.agent_mode:
            return None
        selected = self.image_handler.choose_auto_image_candidate(candidates)
        if selected is not None:
            selected["selection_source"] = "heuristic"
            selected["selection_reason"] = self.image_handler.selection_reason(selected)
        return selected

    @staticmethod
    def _is_confirmed_image_selection(
        entry: dict[str, Any], candidate: Optional[dict[str, Any]]
    ) -> bool:
        """Return whether a persisted choice is an explicit human/agent choice.

        ``llm`` and ``heuristic`` are legacy/runtime-generated decisions.  An
        entry with no selection metadata remains compatible with older manual
        selection files.
        """
        if not entry.get("selected_image") or candidate is None:
            return False
        sources = {
            entry.get("selection_source"),
            candidate.get("selection_source"),
        }
        if "llm" in sources or "heuristic" in sources:
            return False
        return True

    @staticmethod
    def _candidate_local_path(date: str, path: str) -> Path:
        candidate_path = Path(path)
        if candidate_path.is_absolute():
            return candidate_path
        if candidate_path.parts and candidate_path.parts[0].lower() == "images":
            return media_images_dir(date) / Path(*candidate_path.parts[1:])
        return candidate_path

    def _image_selection_task(
        self,
        item: Any,
        candidates: list[dict[str, Any]],
        date: str,
        selection_path: Path,
    ) -> dict[str, Any]:
        task_candidates = []
        for candidate in candidates:
            path = candidate.get("path")
            if not path:
                continue
            task_candidate = dict(candidate)
            task_candidate["local_path"] = str(
                self._candidate_local_path(date, str(path)).resolve()
            ).replace("\\", "/")
            task_candidates.append(task_candidate)
        return {
            "story_id": str(item.source_id),
            "title": item.title or "",
            "url": item.url or "",
            "selection_file": str(selection_path).replace("\\", "/"),
            "candidates": task_candidates,
        }

    def _load_image_selection(self, content: ContentPackage, date: str) -> set:
        sel_path = pipeline_path(date, "image_selection.json")
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
                    selected_candidate = next(
                        (
                            candidate
                            for candidate in entry.get("candidates", [])
                            if candidate.get("path") == chosen
                        ),
                        None,
                    )
                    if self.agent_mode and not self._is_confirmed_image_selection(
                        entry, selected_candidate
                    ):
                        continue
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
        self.pending_image_selections = []
        sel_path = pipeline_path(date, "image_selection.json")
        existed = sel_path.exists()
        data: Dict[str, Any] = {"date": date, "items": {}}
        if existed:
            try:
                with open(sel_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                data = cast(Dict[str, Any], raw)
                data.setdefault("date", date)
                data.setdefault("items", {})
            except Exception as e:
                self.logger.info(f"Failed to merge image selection, regenerating: {e}")
                data = {"date": date, "items": {}}

        changed = False
        for item in content.items:
            if not item.image_candidates:
                continue
            setattr(item, "_content_date", date)
            key = str(item.source_id)
            existing_entry = data["items"].get(key, {})  # type: ignore[union-attr]
            candidates = self.image_handler.merge_image_candidates(
                existing_entry.get("candidates", []),
                item.image_candidates,
            )
            selected = existing_entry.get("selected_image")
            existing_selected_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.get("path") == selected
                ),
                None,
            )
            confirmed = self._is_confirmed_image_selection(
                existing_entry, existing_selected_candidate
            )
            reselection_required = (
                not selected
                or (self.agent_mode and not confirmed)
                or (
                    not self.agent_mode
                    and existing_selected_candidate is not None
                    and existing_selected_candidate.get("selection_source") == "llm"
                )
            )
            selected_candidate = None
            if reselection_required:
                if existing_selected_candidate is not None and not self.agent_mode:
                    for candidate in candidates:
                        candidate.pop("selection_source", None)
                        candidate.pop("selection_reason", None)
                selected_candidate = self._select_image_candidate(item, candidates)
                selected = (
                    selected_candidate.get("path") if selected_candidate else None
                )
            else:
                selected_candidate = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.get("path") == selected
                    ),
                    None,
                )
            if selected:
                for candidate in candidates:
                    candidate["auto_selected"] = (
                        False if self.agent_mode else candidate.get("path") == selected
                    )
                if selected_candidate is not None:
                    selected_candidate.setdefault(
                        "selection_reason",
                        self.image_handler.selection_reason(selected_candidate),
                    )
                existing = [p for p in item.article_images if p != selected]
                item.article_images = [selected] + existing
            elif self.agent_mode:
                for candidate in candidates:
                    candidate.pop("auto_selected", None)
                self.pending_image_selections.append(
                    self._image_selection_task(item, candidates, date, sel_path)
                )
            new_entry = {
                "title": item.title,
                "url": item.url,
                "candidates": candidates,
                "selected_image": selected,
            }
            for metadata_key in ("selection_source", "selection_reason"):
                if metadata_key in existing_entry:
                    new_entry[metadata_key] = existing_entry[metadata_key]
            if existing_entry != new_entry:
                data["items"][key] = new_entry  # type: ignore[union-attr]
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
        items_dict: Dict[str, Dict[str, Any]] = {}
        for item in content.items:
            if item.article_text is not None or item.article_summary is not None:
                items_dict[str(item.source_id)] = {
                    "article_text": item.article_text,
                    "article_images": item.article_images,
                    "article_summary": item.article_summary,
                    "article_relevance_score": item.article_relevance_score,
                    "editor_angle": item.editor_angle,
                    "dek": item.dek,
                    "key_points": item.key_points,
                    "keywords": item.keywords,
                    "category": item.category,
                    "why_it_matters": item.why_it_matters,
                    "enrichment_source": item.enrichment_source,
                    "enrichment_error": item.enrichment_error,
                    "logo_image": item.logo_image,
                    "screenshot_image": item.screenshot_image,
                    "image_candidates": item.image_candidates,
                }
        data: Dict[str, Any] = {"date": content.date, "items": items_dict}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.debug(f"Saved enrichment cache to {cache_path}")

    def _load_from_cache(self, content: ContentPackage, cache_path: Path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items_cache = data.get("items", {})
            skipped_incomplete = 0
            for item in content.items:
                cached = items_cache.get(str(item.source_id))
                if cached:
                    # Skip cached entries where fetch succeeded but LLM
                    # enrichment failed — they need a re-run.
                    if cached.get("article_text") and not cached.get("editor_angle"):
                        skipped_incomplete += 1
                        continue
                    item.article_text = cached.get("article_text")
                    item.article_images = cached.get("article_images", [])
                    item.article_summary = cached.get("article_summary")
                    item.article_relevance_score = cached.get("article_relevance_score")
                    item.editor_angle = cached.get("editor_angle")
                    item.dek = cached.get("dek")
                    item.key_points = cached.get("key_points")
                    item.category = cached.get("category")
                    item.why_it_matters = cached.get("why_it_matters")
                    item.keywords = self._normalize_keywords(
                        cached.get("keywords"),
                        category=item.category,
                        fallback_values=[
                            item.editor_angle,
                            item.dek,
                            item.why_it_matters,
                            item.title,
                        ],
                    )
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
            if skipped_incomplete:
                self.logger.info(
                    f"Skipped {skipped_incomplete} cached items with "
                    f"missing editor_angle (will re-enrich)"
                )
            self.logger.debug(f"Loaded {loaded} cached enrichments from {cache_path}")
        except Exception as e:
            self.logger.info(f"Failed to load enrichment cache: {e}")
