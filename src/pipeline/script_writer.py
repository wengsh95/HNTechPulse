import json
import time
from pathlib import Path
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.core.models import Script, ScriptSegment, ContentPackage, ContentItem, SelectionResult
from src.core.interfaces import LLMProvider
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.comment_judgement import (
    candidate_ids_for_story,
    comment_judgement_key,
    load_comment_judgements,
)
from src.pipeline.comment_selection import select_quote_comments
from src.utils.logger import setup_logger
from src.core.models import SceneElement, Cue


class ScriptWriter:
    def __init__(
        self,
        config: dict,
        llm_provider: LLMProvider,
        content_preparer: Optional[ContentPreparer] = None,
        debug: bool = False,
    ):
        self.config = config
        self.llm_provider = llm_provider
        self.content_preparer = content_preparer
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    @staticmethod
    def _story_angle_from_segment(segment: ScriptSegment) -> dict:
        """Extract the product-facing angle fields from an LLM story segment."""
        event_elem = next(
            (elem for elem in segment.scene_elements if elem.element_type == "event_card"),
            None,
        )
        props = event_elem.props if event_elem else {}
        return {
            "editor_angle": props.get("editor_angle") or "",
            "dek": props.get("dek") or "",
            "key_points": props.get("key_points") or [],
            "event_summary": props.get("event_summary") or "",
            "why_it_matters": props.get("why_it_matters") or "",
            "next_watch": props.get("next_watch") or "",
            "category": props.get("category") or "",
            "keywords": props.get("keywords") or [],
        }

    def _generate_fixed_opening(
        self,
        date: str,
        selection: Optional[SelectionResult] = None,
        content: Optional[ContentPackage] = None,
        story_scan_segs: Optional[list[ScriptSegment]] = None,
    ) -> ScriptSegment:
        """Generate a short positioning line before the first story."""
        from datetime import datetime
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_display = date_obj.strftime("%Y年%m月%d日")
        except (ValueError, TypeError):
            date_display = date

        audio_text = "早上好，这里是 HN TechPulse，带你看昨天HN发生了什么。"
        duration = 4

        return ScriptSegment(
            segment_type="opening",
            audio_text=audio_text,
            estimated_duration=duration,
            emotion="warm",
            scene_elements=[
                SceneElement(
                    element_type="title_card",
                    start_time=0.0,
                    end_time=float(duration),
                    props={
                        "title": "HN TechPulse",
                        "subtitle": date_display,
                        "headline": "HNTechPulse",
                        "topics": [],
                        "stats": "",
                    }
                )
            ],
            cues=[
                Cue(text=audio_text, start_time=0.0, end_time=float(duration))
            ],
            meta={}
        )

    def _opening_needs_refresh(self, segment: ScriptSegment) -> bool:
        """Detect cached openings that still preview the top stories."""
        audio_text = segment.audio_text or ""
        if "：" in audio_text or "这几件事" in audio_text or "几个技术信号" in audio_text:
            return True

        for elem in segment.scene_elements:
            if elem.element_type == "title_card" and elem.props.get("topics"):
                return True

        return False

    def _generate_fixed_closing(self, date: str) -> ScriptSegment:
        """生成每日快讯结尾"""
        from datetime import datetime
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday = date_obj.weekday()
        except (ValueError, TypeError):
            weekday = None

        if weekday == 4:
            audio_text = "好，今天的速览就到这里，周末愉快，多喝热水。"
        elif weekday == 5:
            audio_text = "好，今天的速览就到这里，周末继续愉快，多喝热水。"
        elif weekday == 6:
            audio_text = "好，今天的速览就到这里，新的一周加油，多喝热水。"
        else:
            audio_text = "好，今天的速览就到这里，下期再见，多喝热水。"
        duration = 8

        return ScriptSegment(
            segment_type="closing",
            audio_text=audio_text,
            estimated_duration=duration,
            emotion="warm",
            scene_elements=[
                SceneElement(
                    element_type="closing_card",
                    start_time=0.0,
                    end_time=float(duration),
                    props={}
                )
            ],
            cues=[
                Cue(text=audio_text, start_time=0.0, end_time=float(duration))
            ],
            meta={}
        )

    def _generate_dashboard_segment(
        self,
        selection: SelectionResult,
        content: ContentPackage,
        story_scan_segs: Optional[list[ScriptSegment]] = None,
    ) -> ScriptSegment:
        """Generate the dashboard as a video guide, not a dense ranking table."""
        entries = []
        angle_by_story = {}
        for idx, seg in enumerate(story_scan_segs or []):
            angle = self._story_angle_from_segment(seg)
            story_index = None
            for elem in seg.scene_elements:
                if elem.props and "story_index" in elem.props:
                    story_index = elem.props.get("story_index")
                    break
            if story_index is None and idx < len(selection.brief_items):
                story_index = selection.brief_items[idx].get("story_index")
            if story_index is not None:
                angle_by_story[int(story_index)] = angle

        for i, bi in enumerate(selection.brief_items):
            story_idx = bi.get("story_index")
            if story_idx is not None and story_idx < len(content.items):
                item = content.items[story_idx]
                angle = angle_by_story.get(story_idx, {})
                entries.append({
                    "rank": i + 1,
                    "story_index": story_idx,
                    "original_title": item.title,
                    "title_translation": item.title_cn,
                    "editor_angle": angle.get("editor_angle") or angle.get("dek") or angle.get("event_summary") or item.title_cn or item.title,
                    "why_it_matters": angle.get("why_it_matters") or "",
                    "next_watch": angle.get("next_watch") or "",
                    "category": angle.get("category") or "",
                    "keywords": angle.get("keywords") or [],
                    "score": item.score,
                    "comment_count": item.comment_count,
                })

        dashboard_duration = 8.0
        focus_count = min(3, len(entries))
        audio_text = "来看今天的热度排行。对于感兴趣的话题，可以通过下方进度条快速跳转。"

        return ScriptSegment(
            segment_type="dashboard",
            audio_text=audio_text,
            estimated_duration=dashboard_duration,
            emotion="neutral",
            scene_elements=[
                SceneElement(
                    element_type="dashboard_card",
                    start_time=0.0,
                    end_time=dashboard_duration,
                    props={
                        "entries": entries,
                        "mode": "guide",
                        "focus_count": focus_count,
                    }
                )
            ],
            cues=[
                Cue(text=audio_text, start_time=0.0, end_time=dashboard_duration)
            ],
            meta={"dashboard": {"entries": entries}}
        )

    def _generate_script_split(self, content: ContentPackage, selection: SelectionResult, date: str) -> Script:
        """生成每日快讯脚本（拆分模式）"""

        segments = []

        # Generate story scans first so opening/dashboard can lead with concrete angles.
        story_indices = [
            bi.get("story_index")
            for bi in selection.brief_items
            if bi.get("story_index") is not None
        ]
        story_scan_segs_by_index = {}
        comment_judgements = load_comment_judgements(date)
        max_workers = int(self.config.get("llm", {}).get("max_workers", 1) or 1)
        max_workers = max(1, min(max_workers, len(story_indices) or 1))

        def _generate_story_scan(story_idx: int) -> ScriptSegment:
            item = content.items[story_idx]
            judgement = comment_judgements.get(comment_judgement_key(item), {})
            return self.llm_provider.generate_single_story_segment(
                content=content,
                story_index=story_idx,
                segment_type="story_scan_item",
                prompt_template_path="prompts/single_story_scan.md",
                date=date,
                comments_data=judgement or None
            )

        if max_workers == 1 or len(story_indices) <= 1:
            for story_idx in story_indices:
                story_scan_segs_by_index[story_idx] = _generate_story_scan(story_idx)
        else:
            self.logger.info(
                f"Generating {len(story_indices)} story scans with {max_workers} LLM workers"
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_generate_story_scan, story_idx): story_idx
                    for story_idx in story_indices
                }
                for future in as_completed(futures):
                    story_idx = futures[future]
                    story_scan_segs_by_index[story_idx] = future.result()

        story_scan_segs = [
            story_scan_segs_by_index[story_idx]
            for story_idx in story_indices
            if story_idx in story_scan_segs_by_index
        ]
        for story_idx, seg in zip(story_indices, story_scan_segs):
            self._normalize_quote_card_selection(
                seg,
                content.items[story_idx],
                comment_judgements.get(comment_judgement_key(content.items[story_idx]), {}),
            )

        # 固定开场
        segments.append(self._generate_fixed_opening(date, selection, content, story_scan_segs))

        # Dashboard
        segments.append(self._generate_dashboard_segment(selection, content, story_scan_segs))

        # Story scan
        if not story_scan_segs:
            self.logger.info(
                f"WARNING: No story_scan segments generated for {len(content.items)} "
                f"content items. Video will have no news content in the middle."
            )
        else:
            combined_audio = ""
            combined_scene_elements = []
            sub_segment_char_ranges = []  # [(start, end), ...] per-card char offsets
            sub_idx = 0
            for story_i, s in enumerate(story_scan_segs):
                card_narrations = s.meta.get("card_narrations", [])
                if not card_narrations:
                    # Fallback: no card_narrations, treat entire story as one block
                    char_start = len(combined_audio)
                    if combined_audio:
                        combined_audio += " "
                    combined_audio += s.audio_text
                    char_end = len(combined_audio)
                    sub_segment_char_ranges.append((char_start, char_end))
                    for elem in s.scene_elements:
                        elem.sub_segment_index = sub_idx
                        if elem.element_type == "event_card":
                            elem.props["display_index"] = story_i
                            elem.props["story_count"] = len(story_scan_segs)
                        combined_scene_elements.append(elem)
                    sub_idx += 1
                    continue

                # Card-level processing: each card_narration → own char_range + sub_segment_index
                for card in card_narrations:
                    card_audio = card.get("audio_text", "")
                    card_type = card.get("card_type", "")
                    if not card_audio:
                        continue

                    char_start = len(combined_audio)
                    if combined_audio:
                        combined_audio += " "
                    combined_audio += card_audio
                    char_end = len(combined_audio)
                    sub_segment_char_ranges.append((char_start, char_end))

                    # Find matching scene_element
                    matched = False
                    for elem in s.scene_elements:
                        if elem.element_type == card_type and elem.sub_segment_index is None:
                            elem.sub_segment_index = sub_idx
                            if elem.element_type == "event_card":
                                elem.props["display_index"] = story_i
                                elem.props["story_count"] = len(story_scan_segs)
                            combined_scene_elements.append(elem)
                            matched = True
                            break

                    if not matched:
                        self.logger.debug(
                            f"card_narration type '{card_type}' has no matching scene_element in story {story_i}"
                        )

                    sub_idx += 1

            total_duration = sum(s.estimated_duration for s in story_scan_segs)

            story_scan_seg = ScriptSegment(
                segment_type="story_scan",
                audio_text=combined_audio,
                estimated_duration=total_duration,
                emotion="upbeat",
                scene_elements=combined_scene_elements,
                meta={
                    "sub_segment_estimated_durations": [s.estimated_duration for s in story_scan_segs],
                    "sub_segment_char_ranges": sub_segment_char_ranges,
                },
            )
            segments.append(story_scan_seg)

        # 固定结尾
        segments.append(self._generate_fixed_closing(date))

        return Script(
            title="HN TechPulse 每日快讯",
            description=f"每日快讯 - {date}",
            tags=[],
            segments=segments)

    @staticmethod
    def _normalize_quote_card_selection(segment: ScriptSegment, item: ContentItem, judgement: dict) -> None:
        preferred_ids = candidate_ids_for_story(judgement, max_n=12)
        for elem in segment.scene_elements:
            if elem.element_type != "quote_card":
                continue
            props = elem.props or {}
            selected_ids = props.get("selected_comment_ids") or []
            combined_ids = list(selected_ids)
            for comment_id in preferred_ids:
                if comment_id not in combined_ids:
                    combined_ids.append(comment_id)
            selected_comments = select_quote_comments(
                item.comments,
                selected_ids=combined_ids,
                max_n=3,
            )
            props["selected_comment_ids"] = [
                str(c.source_id)
                for c in selected_comments
                if c.source_id is not None
            ]
            elem.props = props

    def write(self, content: ContentPackage) -> Script:
        t_total = time.monotonic()

        # Script checkpoint: if script.json already exists, skip all LLM work.
        script_path = Path(f"data/{content.date}/script.json")
        if script_path.exists():
            self.logger.info(f"Found existing {script_path}, loading...")
            script = self.load_script(content.date)
            opening_segment = next(
                (seg for seg in script.segments if seg.segment_type == "opening"),
                None,
            )
            if opening_segment and self._opening_needs_refresh(opening_segment):
                self.logger.info("Cached opening uses topic preview, refreshing opening only")
                refreshed_opening = self._generate_fixed_opening(content.date)
                script.segments = [
                    refreshed_opening if seg.segment_type == "opening" else seg
                    for seg in script.segments
                ]
            # Validate cached script has story content when content items exist.
            # A broken cache (e.g. from a prior failed run) would be missing the
            # story_scan segment, producing a video with no news content.
            has_story_scan = any(
                seg.segment_type == "story_scan" for seg in script.segments
            )
            if content.items and not has_story_scan:
                self.logger.info(
                    "Cached script is missing story_scan segment — "
                    "forcing regeneration"
                )
                script_path.unlink()
            elif not self._validate_cache_metadata(script, content):
                self.logger.info(
                    "Cached script is missing timing metadata — "
                    "forcing regeneration"
                )
                script_path.unlink()
            else:
                elapsed = time.monotonic() - t_total
                self.logger.info(f"Script loaded from cache in {elapsed:.1f}s")
                return script

        self.logger.info(f"Input: {len(content.items)} stories, date={content.date}")

        # Build selection from top N stories (already sorted by score descending).
        # No LLM decision needed — score/comment-count ranking is sufficient.
        num_brief = self.config.get("pipeline", {}).get("num_brief_items", 6)
        brief_items = [
            {"story_index": i} for i in range(min(num_brief, len(content.items)))
        ]
        selection = SelectionResult(
            brief_items=brief_items,
            raw_json=json.dumps({"brief_items": brief_items}, ensure_ascii=False),
        )

        self.logger.info(f"Selection: {len(brief_items)} stories by score ranking")
        self.logger.info("Round 2: Script generation (split mode)")
        script = self._generate_script_split(
            content=content,
            selection=selection,
            date=content.date
        )

        elapsed = time.monotonic() - t_total
        self.logger.info("=" * 60)
        self.logger.info(f"Pipeline complete in {elapsed:.1f}s (with checkpoint recovery)")
        self.logger.info("=" * 60)

        return script

    def save_script(self, script: Script, date: str) -> None:
        path = Path(f"data/{date}/script.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        script_dict = asdict(script)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Saved script to {path}")

    def generate_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> str:
        return self._generate_brief_transcript(script, date, content)

    def _generate_brief_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> str:
        """Generate newsletter-style markdown for daily brief product (4-segment structure)."""
        lines = [f"# HN TechPulse 每日快讯 | {date}", ""]
        if script.description:
            lines.append(f"> {script.description}")
        if script.total_duration:
            mins = int(script.total_duration) // 60
            secs = int(script.total_duration) % 60
            lines.append(f"> 视频时长 {mins}:{secs:02d}")
        lines.append("")

        opening_segment = None
        dashboard_segment = None
        scan_segment = None
        closing_segment = None

        for seg in script.segments:
            if seg.segment_type == "opening":
                opening_segment = seg
            elif seg.segment_type == "dashboard":
                dashboard_segment = seg
            elif seg.segment_type == "story_scan":
                scan_segment = seg
            elif seg.segment_type == "closing":
                closing_segment = seg

        # Opening
        if opening_segment:
            lines.append("---")
            lines.append("")
            lines.append("## 开场")
            lines.append("")
            lines.append(opening_segment.audio_text)
            lines.append("")

        # Dashboard (top10 list)
        if dashboard_segment:
            dashboard_entries = []
            for elem in dashboard_segment.scene_elements:
                if elem.element_type == "dashboard_card":
                    dashboard_entries = elem.props.get("entries", [])
                    break

            lines.append("---")
            lines.append("")
            lines.append("## 热度仪表盘")
            lines.append("")

            if dashboard_entries:
                for entry in dashboard_entries:
                    rank = entry.get("rank", "")
                    title = entry.get("original_title", "") or entry.get("title", "")
                    title_cn = entry.get("title_translation", "") or entry.get("title_cn", "")
                    score = entry.get("score", "")
                    comments = entry.get("comment_count", "")
                    score_str = f" ▲ {score}" if score else ""
                    comments_str = f" · 💬 {comments}" if comments else ""
                    if title_cn:
                        lines.append(f"{rank}. **{title_cn}** / {title}{score_str}{comments_str}")
                    else:
                        lines.append(f"{rank}. **{title}**{score_str}{comments_str}")
            elif content:
                for i, item in enumerate(content.items[:10], 1):
                    score_str = f" ▲ {item.score}" if item.score else ""
                    comments_str = f" · 💬 {item.comment_count}" if item.comment_count else ""
                    title_cn = item.title_cn
                    if title_cn:
                        lines.append(f"{i}. **{title_cn}** / {item.title}{score_str}{comments_str}")
                    else:
                        lines.append(f"{i}. **{item.title}**{score_str}{comments_str}")
            lines.append("")

        # Story scan (逐条速览)
        if scan_segment:
            # Group scene_elements by story_index
            story_elems: dict = {}
            for elem in scan_segment.scene_elements:
                si = elem.props.get("story_index") if elem.props else None
                if si is not None:
                    story_elems.setdefault(si, []).append(elem)

            # Split audio_text per card using sub_segment_char_ranges
            char_ranges = scan_segment.meta.get("sub_segment_char_ranges", []) if scan_segment.meta else []
            card_texts = []
            if char_ranges and scan_segment.audio_text:
                for start, end in char_ranges:
                    card_texts.append(scan_segment.audio_text[start:end].strip())

            lines.append("---")
            lines.append("")
            lines.append("## 逐条速览")
            lines.append("")

            def _fmt_time(seconds):
                if seconds is None:
                    return ""
                m = int(seconds) // 60
                s = int(seconds) % 60
                return f"{m}:{s:02d}"

            card_idx = 0
            for i in sorted(story_elems.keys()):
                elems = story_elems[i]
                item = content.items[i] if content and i < len(content.items) else None

                event_elem = next((e for e in elems if e.element_type == "event_card"), None)
                atmosphere_elem = next((e for e in elems if e.element_type == "atmosphere_card"), None)
                quote_elem = next((e for e in elems if e.element_type == "quote_card"), None)

                event_summary = event_elem.props.get("dek", "") or event_elem.props.get("event_summary", "") if event_elem else ""
                display_idx = event_elem.props.get("display_index", i) if event_elem else i

                lines.append(f"### {display_idx + 1}. {event_summary or (item.title if item else '')}")
                lines.append("")

                # Card-by-card narration
                for _ in range(len([e for e in elems if e.element_type in ("event_card", "atmosphere_card", "quote_card")])):
                    if card_idx < len(card_texts):
                        lines.append(card_texts[card_idx])
                        lines.append("")
                    card_idx += 1

                # Meta info
                meta_parts = []
                image_parts = []
                if item:
                    if item.score:
                        meta_parts.append(f"▲ {item.score}")
                    if item.comment_count:
                        meta_parts.append(f"💬 {item.comment_count}")
                    if item.url:
                        meta_parts.append(f"[原文]({item.url})")
                    if item.article_images:
                        for img in item.article_images:
                            image_parts.append(f"🖼 {img}")
                    if item.screenshot_image:
                        image_parts.append(f"📸 {item.screenshot_image}")
                    if item.logo_image:
                        image_parts.append(f"🏷 {item.logo_image}")
                if meta_parts:
                    lines.append(" · ".join(meta_parts))
                    lines.append("")
                if image_parts:
                    lines.append(" · ".join(image_parts))
                    lines.append("")

                # Stance distribution from atmosphere_card
                if atmosphere_elem and atmosphere_elem.props:
                    dist = atmosphere_elem.props.get("stance_distribution", {})
                    if dist:
                        sorted_dist = sorted(dist.items(), key=lambda x: x[1], reverse=True)
                        dist_str = " · ".join(f"{k} {int(v * 100)}%" for k, v in sorted_dist if v > 0)
                        if dist_str:
                            lines.append(f"**社区观点**  {dist_str}")
                            lines.append("")

                # Debate focus from atmosphere_card
                if atmosphere_elem and atmosphere_elem.props:
                    debate_focus = atmosphere_elem.props.get("debate_focus", [])
                    if debate_focus:
                        lines.append(f"**争议焦点**  {' · '.join(debate_focus)}")
                        lines.append("")

                # Quotes from quote_card
                if quote_elem and quote_elem.props:
                    quotes = quote_elem.props.get("quotes", [])
                    if quotes:
                        for q in quotes:
                            stance = q.get("stance", "")
                            author = q.get("author", "")
                            text = q.get("text", "")
                            stance_str = f"**[{stance}]** " if stance else ""
                            lines.append(f"- {stance_str}{author}: \"{text[:120]}\"")
                        lines.append("")
            else:
                if not story_elems and scan_segment.audio_text:
                    lines.append(scan_segment.audio_text)
                    lines.append("")

        # Closing
        if closing_segment:
            lines.append("---")
            lines.append("")
            lines.append("## 结尾")
            lines.append("")
            lines.append(closing_segment.audio_text)
            lines.append("")

        return "\n".join(lines)

    def save_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> Path:
        path = Path(f"data/{date}/transcript.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        md_content = self.generate_transcript(script, date, content)
        path.write_text(md_content, encoding="utf-8")
        self.logger.info(f"Saved transcript to {path}")
        return path

    def load_script(self, date: str) -> Script:
        path = Path(f"data/{date}/script.json")
        if not path.exists():
            raise FileNotFoundError(f"Script not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                script_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Script file {path} contains invalid JSON: {e}") from e

        try:
            return Script(
                title=script_dict["title"],
                description=script_dict["description"],
                tags=script_dict["tags"],
                segments=[
                    ScriptSegment(
                        segment_type=s["segment_type"],
                        audio_text=s["audio_text"],
                        estimated_duration=s["estimated_duration"],
                        actual_duration=s.get("actual_duration"),
                        emotion=s.get("emotion", "neutral"),
                        scene_elements=[
                            SceneElement(
                                element_type=e["element_type"],
                                start_time=e["start_time"],
                                end_time=e["end_time"],
                                props=e["props"],
                                sub_segment_index=e.get("sub_segment_index"),
                            )
                            for e in s.get("scene_elements", [])
                        ],
                        meta=s.get("meta", {}),
                        start_time=s.get("start_time"),
                        end_time=s.get("end_time"),
                        audio_path=s.get("audio_path"),
                        cues=[
                            Cue(
                                text=c["text"],
                                start_time=c["start_time"],
                                end_time=c["end_time"],
                            )
                            for c in s.get("cues", [])
                        ],
                    )
                    for s in script_dict["segments"]
                ],
                total_duration=script_dict.get("total_duration"),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"Script file {path} has unexpected structure: {e}") from e

    def _validate_cache_metadata(self, script: Script, content) -> bool:
        """Check cached script has timing metadata needed for card/cue alignment.

        Returns False if the cache is stale and should be regenerated.
        """
        story_scan = next(
            (s for s in script.segments if s.segment_type == "story_scan"), None
        )
        if story_scan is None:
            return True  # No story_scan to validate

        # Must have char_ranges for TTS-based timing
        if not story_scan.meta.get("sub_segment_char_ranges"):
            return False

        # Milestone 2: story cards need editable fields for productized narrative.
        for elem in story_scan.scene_elements:
            if elem.element_type == "event_card":
                if not elem.props.get("editor_angle"):
                    return False
                if not (elem.props.get("dek") or elem.props.get("event_summary")):
                    return False
                if not elem.props.get("key_points"):
                    return False

        # Scene elements must know their sub-segment index
        for elem in story_scan.scene_elements:
            if elem.sub_segment_index is None:
                return False

        return True
