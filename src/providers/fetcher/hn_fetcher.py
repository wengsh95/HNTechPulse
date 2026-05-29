import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Union

import aiohttp
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.providers.fetcher.models import HNStory, HNComment
from src.core.models import ContentItem, ContentComment, ContentPackage
from src.core.interfaces import ContentFetcher
from src.utils.logger import setup_logger
from src.utils.async_helper import run_async as _run_async


class HNFetcher(ContentFetcher):
    def __init__(
        self,
        config: dict,
        debug: bool = False,
        log_level: Optional[Union[str, int]] = None,
    ):
        self.config = config
        self.debug = debug

        if log_level is None and debug:
            log_level = logging.DEBUG

        self.logger = setup_logger(__name__, debug=debug, level=log_level)
        self.base_url = config.get("hn", {}).get(
            "base_url", "https://hacker-news.firebaseio.com/v0"
        )
        self.top_stories_count = config.get("hn", {}).get("top_stories_count", 100)
        self.target_stories_count = config.get("hn", {}).get("target_stories_count", 10)

        _raw_timeout = config.get("hn", {}).get("request_timeout", (5, 15))
        if isinstance(_raw_timeout, (list, tuple)):
            self.request_timeout = tuple(_raw_timeout)
        elif isinstance(_raw_timeout, (int, float)):
            self.request_timeout = (_raw_timeout, _raw_timeout)
        else:
            self.request_timeout = _raw_timeout

        self.comment_log_interval = config.get("hn", {}).get("comment_log_interval", 50)
        self.max_comment_depth = config.get("hn", {}).get("max_comment_depth", 5)
        self.max_concurrent_requests = config.get("hn", {}).get(
            "max_concurrent_requests", 20
        )
        self.max_retries = config.get("hn", {}).get("max_retries", 3)
        self.granular_cache = config.get("hn", {}).get("granular_cache", True)

        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            pool_block=True,
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def fetch(
        self,
        date: str,
        num_deep_dive: int = 1,
        num_brief: int = 2,
        **kwargs,
    ) -> ContentPackage:
        import time as _time

        t0 = _time.monotonic()
        self.logger.info("=" * 60)
        self.logger.info(f"Starting fetch, date={date}")
        self.logger.info("=" * 60)

        raw_stories_path = Path(f"data/{date}/raw_stories.json")
        # Backward compat: also check old raw.json
        raw_compat_path = Path(f"data/{date}/raw.json")
        cache_path = raw_stories_path if raw_stories_path.exists() else raw_compat_path

        if cache_path.exists():
            self.logger.info(f"Cache hit, loading from {cache_path}")
            result = self._load_stories_from_cache(cache_path, date)
            self.logger.info(f"Loaded from cache in {_time.monotonic() - t0:.1f}s")
            return result

        self.logger.info(
            f"[1/3] Fetching top stories IDs (max {self.top_stories_count})..."
        )
        t1 = _time.monotonic()
        top_story_ids = self._fetch_top_stories()
        self.logger.info(
            f"[1/3] Fetched {len(top_story_ids)} story IDs in {_time.monotonic() - t1:.1f}s"
        )

        total_ids = len(top_story_ids)
        self.logger.info(
            f"[2/3] Fetching story details, total {total_ids} (concurrent={self.max_concurrent_requests})..."
        )
        t2 = _time.monotonic()
        stories = self._fetch_stories_concurrent(top_story_ids)
        valid_count = len(stories)
        skipped_count = total_ids - valid_count
        self.logger.info(
            f"[2/3] Fetched {valid_count} valid stories, skipped {skipped_count}"
            f" in {_time.monotonic() - t2:.1f}s"
        )

        self.logger.info(
            f"[3/3] Filtering by time and selecting top {self.target_stories_count}..."
        )
        t3 = _time.monotonic()
        filtered_stories = self._filter_stories_by_time(stories, date)
        self.logger.info(
            f"  Filtered: {len(stories)} → {len(filtered_stories)} stories (within target date range)"
        )
        top_stories = self._select_top_stories(filtered_stories)
        self.logger.info(
            f"[3/3] Selected {len(top_stories)} stories in {_time.monotonic() - t3:.1f}s"
        )

        # Save stories cache (no comments)
        raw_data = {
            "date": date,
            "stories": [self._story_to_dict(s) for s in top_stories],
        }
        raw_stories_path.parent.mkdir(parents=True, exist_ok=True)
        with open(raw_stories_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Stories cache saved to {raw_stories_path}")

        elapsed = _time.monotonic() - t0
        self.logger.info("=" * 60)
        self.logger.info(
            f"Fetch complete: stories={len(top_stories)}  total_time={elapsed:.1f}s"
        )
        self.logger.info("=" * 60)

        return self._to_content_package(top_stories, {}, date)

    def fetch_comments(self, content: ContentPackage, date: str) -> ContentPackage:
        """Fetch comments for stories in content.items (called after prefilter)."""
        import time as _time

        if not content.items:
            return content

        # Build HNStory list from content items for comment fetching
        stories_to_fetch = []
        for item in content.items:
            # Skip stories that already have comments loaded
            if item.comments:
                continue
            stories_to_fetch.append(
                HNStory(
                    id=int(item.source_id),
                    title=item.title or "",
                    url=item.url,
                    score=item.score or 0,
                    descendants=item.comment_count or 0,
                    time=item.published_at or 0,
                )
            )

        if not stories_to_fetch:
            self.logger.info("All stories already have comments, skipping fetch")
            return content

        self.logger.info(
            f"Fetching comments for {len(stories_to_fetch)} stories"
            f" (concurrent={self.max_concurrent_requests}, max_depth={self.max_comment_depth})..."
        )
        t0 = _time.monotonic()
        comments = self._fetch_comments_concurrent(stories_to_fetch)

        total_comments = sum(len(v) for v in comments.values())
        elapsed = _time.monotonic() - t0
        self.logger.info(f"Fetched {total_comments} comments in {elapsed:.1f}s")

        # Attach comments to content items
        for item in content.items:
            story_id = int(item.source_id)
            for hn_comment in comments.get(story_id, []):
                item.comments.append(
                    ContentComment(
                        author=hn_comment.author,
                        content=hn_comment.text,
                        source_id=str(hn_comment.id),
                        upvotes=hn_comment.score,
                        depth=hn_comment.depth,
                        published_at=hn_comment.time,
                    )
                )

        return content

    def _fetch_top_stories(self) -> List[int]:
        url = f"{self.base_url}/topstories.json"
        response = self._session.get(url, timeout=self.request_timeout)
        response.raise_for_status()
        ids = response.json()
        return ids[: self.top_stories_count]

    def _fetch_stories_concurrent(self, story_ids: List[int]) -> List[HNStory]:
        return _run_async(self._async_fetch_stories(story_ids))

    async def _async_fetch_stories(self, story_ids: List[int]) -> List[HNStory]:
        connector = aiohttp.TCPConnector(limit=self.max_concurrent_requests)
        timeout = aiohttp.ClientTimeout(
            sock_connect=self.request_timeout[0],
            sock_read=self.request_timeout[1],
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            semaphore = asyncio.Semaphore(self.max_concurrent_requests)
            tasks = [
                self._async_fetch_story(session, semaphore, sid) for sid in story_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        stories: List[HNStory] = []
        for sid, result in zip(story_ids, results):
            if isinstance(result, Exception):
                self.logger.error(f"  Story id={sid} fetch failed: {result}")
            elif result is not None:
                assert isinstance(result, HNStory), (
                    f"Expected HNStory, got {type(result)}"
                )
                stories.append(result)
        return stories

    async def _async_fetch_story(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        story_id: int,
    ) -> Optional[HNStory]:
        async with semaphore:
            return await self._async_fetch_story_with_retry(session, story_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _async_fetch_story_with_retry(
        self,
        session: aiohttp.ClientSession,
        story_id: int,
    ) -> Optional[HNStory]:
        url = f"{self.base_url}/item/{story_id}.json"
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

        if not data or data.get("deleted") or data.get("dead"):
            return None

        if data.get("type") != "story":
            return None

        return HNStory(
            id=data.get("id", 0),
            title=data.get("title", ""),
            url=data.get("url"),
            score=data.get("score", 0),
            descendants=data.get("descendants", 0),
            time=data.get("time", 0),
            text=data.get("text"),
            by=data.get("by"),
        )

    def _fetch_comments_concurrent(
        self, stories: List[HNStory]
    ) -> Dict[int, List[HNComment]]:
        return _run_async(self._async_fetch_comments(stories))

    async def _async_fetch_comments(
        self, stories: List[HNStory]
    ) -> Dict[int, List[HNComment]]:
        import time as _time

        connector = aiohttp.TCPConnector(limit=self.max_concurrent_requests)
        timeout = aiohttp.ClientTimeout(
            sock_connect=self.request_timeout[0],
            sock_read=self.request_timeout[1],
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            semaphore = asyncio.Semaphore(self.max_concurrent_requests)
            result: Dict[int, List[HNComment]] = {}
            total_stories = len(stories)
            _story_times: List[float] = []

            for s_idx, story in enumerate(stories, start=1):
                t_story_start = _time.monotonic()

                if self.granular_cache:
                    cached = self._load_granular_comment_cache(story.id)
                    if cached is not None:
                        result[story.id] = cached
                        t_story_elapsed = _time.monotonic() - t_story_start
                        _story_times.append(t_story_elapsed)
                        self.logger.info(
                            f"  Story {s_idx}/{total_stories}: id={story.id}"
                            f"  comments={len(cached):>4}  (cached)  time={t_story_elapsed:.1f}s"
                        )
                        continue

                try:
                    story_comments = await self._async_fetch_all_story_comments(
                        session, semaphore, story.id, story.descendants
                    )
                    result[story.id] = story_comments
                    t_story_elapsed = _time.monotonic() - t_story_start
                    _story_times.append(t_story_elapsed)

                    if self.granular_cache:
                        self._save_granular_comment_cache(story.id, story_comments)

                    avg_per_story = sum(_story_times) / len(_story_times)
                    remaining = total_stories - s_idx
                    eta_seconds = avg_per_story * remaining

                    if eta_seconds > 3600:
                        eta_str = f"{eta_seconds / 3600:.1f}h"
                    elif eta_seconds > 60:
                        eta_str = f"{eta_seconds / 60:.1f}m"
                    else:
                        eta_str = f"{eta_seconds:.0f}s"

                    title_short = story.title[:45] + (
                        "..." if len(story.title) > 45 else ""
                    )
                    self.logger.info(
                        f"  Story {s_idx}/{total_stories}: id={story.id}"
                        f"  comments={len(story_comments):>4}  time={t_story_elapsed:.1f}s"
                        f"  ETA≈{eta_str}  title='{title_short}'"
                    )
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                    t_story_elapsed = _time.monotonic() - t_story_start
                    _story_times.append(t_story_elapsed)
                    self.logger.error(
                        f"  Story {s_idx}/{total_stories} id={story.id} failed in {t_story_elapsed:.1f}s: {e}",
                        exc_info=True,
                    )
                    result[story.id] = []

        return result

    async def _async_fetch_all_story_comments(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        story_id: int,
        expected_total: int = 0,
    ) -> List[HNComment]:
        import time as _time

        t_start = _time.monotonic()
        story_data = await self._async_fetch_item(session, semaphore, story_id)
        if not story_data:
            return []

        top_kids: List[int] = story_data.get("kids", [])
        total_top = len(top_kids)
        self.logger.info(
            f"Fetching comments for story={story_id}  top_level={total_top}"
            f"  expected≈{expected_total}  max_depth={self.max_comment_depth}"
        )

        comments: List[HNComment] = []
        queue: deque[Tuple[int, int]] = deque()
        for kid_id in top_kids:
            queue.append((kid_id, 1))

        fetched_count = 0
        last_log_count = 0

        while queue:
            batch: List[Tuple[int, int]] = []
            while queue and len(batch) < self.max_concurrent_requests:
                batch.append(queue.popleft())

            tasks = [
                self._async_fetch_item(session, semaphore, item_id)
                for item_id, _depth in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (item_id, depth), result in zip(batch, results):
                if isinstance(result, Exception):
                    self.logger.debug(
                        f"  [L{depth}] item={item_id} fetch failed: {result}"
                    )
                    continue
                if result is None:
                    continue
                assert isinstance(result, dict), f"Expected dict, got {type(result)}"
                if result.get("deleted") or result.get("dead"):
                    continue

                if result.get("type") == "comment":
                    comment = HNComment(
                        id=result.get("id", 0),
                        author=result.get("by", ""),
                        text=result.get("text", ""),
                        time=result.get("time", 0),
                        score=result.get("score"),
                        depth=depth,
                    )
                    comments.append(comment)
                    fetched_count += 1

                    if depth < self.max_comment_depth:
                        sub_kids = result.get("kids", [])
                        for kid_id in sub_kids:
                            queue.append((kid_id, depth + 1))

                interval = self.comment_log_interval
                if interval > 0 and fetched_count - last_log_count >= interval:
                    elapsed = _time.monotonic() - t_start
                    rate = fetched_count / elapsed if elapsed > 0 else 0.0
                    pct = (
                        (fetched_count / expected_total * 100) if expected_total else 0
                    )
                    self.logger.info(
                        f"  Comments for story={story_id}"
                        f"  fetched={fetched_count:>5}"
                        f"{f'/≈{expected_total}({pct:5.1f}%)' if expected_total else ''}"
                        f"  rate≈{rate:.1f}/s  elapsed={elapsed:.1f}s"
                    )
                    last_log_count = fetched_count

        elapsed = _time.monotonic() - t_start
        self.logger.debug(
            f"  Comments done: story={story_id}"
            f"  actual={len(comments)}  expected≈{expected_total}"
            f"  time={elapsed:.1f}s"
        )
        return comments

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _async_fetch_item(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        item_id: int,
    ) -> Optional[dict]:
        async with semaphore:
            url = f"{self.base_url}/item/{item_id}.json"
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()

    async def _async_fetch_all_story_comments_standalone(
        self,
        story_id: int,
        expected_total: int = 0,
    ) -> List[HNComment]:
        connector = aiohttp.TCPConnector(limit=self.max_concurrent_requests)
        timeout = aiohttp.ClientTimeout(
            sock_connect=self.request_timeout[0],
            sock_read=self.request_timeout[1],
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            semaphore = asyncio.Semaphore(self.max_concurrent_requests)
            return await self._async_fetch_all_story_comments(
                session, semaphore, story_id, expected_total
            )

    def _filter_stories_by_time(
        self, stories: List[HNStory], date_str: str
    ) -> List[HNStory]:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        yesterday_beijing = target_date - timedelta(days=1)

        beijing_tz = timezone(timedelta(hours=8))

        start_beijing = datetime(
            yesterday_beijing.year,
            yesterday_beijing.month,
            yesterday_beijing.day,
            0,
            0,
            0,
            tzinfo=beijing_tz,
        )
        end_beijing = datetime(
            yesterday_beijing.year,
            yesterday_beijing.month,
            yesterday_beijing.day,
            23,
            59,
            59,
            tzinfo=beijing_tz,
        )

        start_timestamp = int(start_beijing.timestamp())
        end_timestamp = int(end_beijing.timestamp())

        self.logger.debug(
            f"  Filter time range (Beijing): {start_beijing} ~ {end_beijing}"
        )
        self.logger.debug(
            f"  Filter timestamp range: {start_timestamp} ~ {end_timestamp}"
        )

        filtered = []
        for story in stories:
            if start_timestamp <= story.time <= end_timestamp:
                filtered.append(story)

        return filtered

    def _select_top_stories(self, stories: List[HNStory]) -> List[HNStory]:
        stories_sorted = sorted(
            stories, key=lambda s: (s.score, s.descendants), reverse=True
        )
        return stories_sorted[: self.target_stories_count]

    def _load_granular_comment_cache(self, story_id: int) -> Optional[List[HNComment]]:
        import time as _time

        cache_dir = Path("data/_comment_cache")
        cache_file = cache_dir / f"{story_id}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cache_time = data.get("cached_at", 0)
            now = _time.time()
            if now - cache_time > 86400:
                self.logger.debug(f"  Comment cache expired for story={story_id}")
                return None

            comments = [self._dict_to_comment(c) for c in data.get("comments", [])]
            self.logger.debug(
                f"  Comment cache hit for story={story_id}: {len(comments)} comments"
            )
            return comments
        except Exception as e:
            self.logger.debug(f"  Comment cache load failed for story={story_id}: {e}")
            return None

    def _save_granular_comment_cache(self, story_id: int, comments: List[HNComment]):
        import time as _time

        cache_dir = Path("data/_comment_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{story_id}.json"

        try:
            data = {
                "story_id": story_id,
                "cached_at": _time.time(),
                "comments": [self._comment_to_dict(c) for c in comments],
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.debug(
                f"  Comment cache saved for story={story_id}: {len(comments)} comments"
            )
        except Exception as e:
            self.logger.debug(f"  Comment cache save failed for story={story_id}: {e}")

    def _to_content_package(
        self,
        stories: List[HNStory],
        comments: Dict[int, List[HNComment]],
        date: str,
    ) -> ContentPackage:
        items: List[ContentItem] = []

        for story in stories:
            item = ContentItem(
                source="hackernews",
                source_id=str(story.id),
                title=story.title,
                url=story.url,
                score=story.score,
                comment_count=story.descendants,
                published_at=story.time,
            )

            for hn_comment in comments.get(story.id, []):
                item.comments.append(
                    ContentComment(
                        author=hn_comment.author,
                        content=hn_comment.text,
                        source_id=str(hn_comment.id),
                        upvotes=hn_comment.score,
                        depth=hn_comment.depth,
                        published_at=hn_comment.time,
                    )
                )

            items.append(item)

        return ContentPackage(
            date=date,
            items=items,
            deep_dive_indices=[],
            brief_indices=list(range(len(items))),
        )

    def _load_stories_from_cache(
        self,
        path: Path,
        date: str,
    ) -> ContentPackage:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        stories = [self._dict_to_story(d) for d in raw_data["stories"]]
        # Old raw.json may include comments; new raw_stories.json won't
        comments = {}
        if "comments" in raw_data:
            comments = {
                int(k): [self._dict_to_comment(c) for c in v]
                for k, v in raw_data["comments"].items()
            }

        return self._to_content_package(stories, comments, date)

    def _story_to_dict(self, story: HNStory) -> dict:
        return {
            "id": story.id,
            "title": story.title,
            "url": story.url,
            "score": story.score,
            "descendants": story.descendants,
            "time": story.time,
            "text": story.text,
            "by": story.by,
        }

    def _dict_to_story(self, d: dict) -> HNStory:
        return HNStory(
            id=d["id"],
            title=d["title"],
            url=d.get("url"),
            score=d["score"],
            descendants=d["descendants"],
            time=d["time"],
            text=d.get("text"),
            by=d.get("by"),
        )

    def _comment_to_dict(self, comment: HNComment) -> dict:
        d = {
            "id": comment.id,
            "author": comment.author,
            "text": comment.text,
            "time": comment.time,
        }
        if comment.score is not None:
            d["score"] = comment.score
        if comment.depth is not None:
            d["depth"] = comment.depth
        return d

    def _dict_to_comment(self, d: dict) -> HNComment:
        return HNComment(
            id=d["id"],
            author=d["author"],
            text=d["text"],
            time=d["time"],
            score=d.get("score"),
            depth=d.get("depth"),
        )
