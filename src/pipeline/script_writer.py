import json
import time
from pathlib import Path
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
from src.pipeline.script_io import save_script as _save_script, load_script as _load_script
from src.pipeline.transcript_generator import (
    generate_brief_transcript as _generate_brief_transcript,
    save_transcript as _save_transcript,
)
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
    def _story_angle_from_segment(segment: ScriptSegment, item=None) -> dict:
        """Extract the product-facing angle fields from an LLM story segment."""
        event_elem = next(
            (elem for elem in segment.scene_elements if elem.element_type == "event_card"),
            None,
        )
        props = event_elem.props if event_elem else {}
        return {
            "editor_angle": props.get("editor_angle") or (item.editor_angle if item else None) or "",
            "dek": props.get("dek") or (item.dek if item else None) or "",
            "key_points": props.get("key_points") or (item.key_points if item else None) or [],
            "event_summary": props.get("event_summary") or (item.dek if item else None) or "",
            "why_it_matters": props.get("why_it_matters") or "",
            "next_watch": props.get("next_watch") or "",
            "category": props.get("category") or (item.category if item else None) or "",
            "keywords": props.get("keywords") or (item.keywords if item else None) or [],
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
        duration = 5

        keywords: list[str] = []
        if story_scan_segs:
            for seg in story_scan_segs[:3]:
                for elem in seg.scene_elements:
                    if elem.element_type == "event_card":
                        kw = elem.props.get("editor_angle") or elem.props.get("title_cn") or ""
                        if kw:
                            keywords.append(str(kw))
                        break

        return ScriptSegment(
            segment_type="opening",
            audio_text=audio_text,
            estimated_duration=duration,
            emotion="warm",
            scene_elements=[
                SceneElement(
                    element_type="cover_card",
                    start_time=0.0,
                    end_time=float(duration),
                    props={
                        "headline": "每日技术速览",
                        "subtitle": date_display,
                        "keywords": keywords[:3],
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
            if elem.element_type == "cover_card" and elem.props.get("topics"):
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
            story_index = None
            for elem in seg.scene_elements:
                if elem.props and "story_index" in elem.props:
                    story_index = elem.props.get("story_index")
                    break
            if story_index is None and idx < len(selection.brief_items):
                story_index = selection.brief_items[idx].get("story_index")
            item = content.items[story_index] if story_index is not None and story_index < len(content.items) else None
            angle = self._story_angle_from_segment(seg, item=item)
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
                prompt_template_path="prompts/story_script.md",
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
            judgement = comment_judgements.get(comment_judgement_key(content.items[story_idx]), {})
            self._normalize_quote_card_selection(
                seg,
                content.items[story_idx],
                judgement,
            )
            self._normalize_atmosphere_card(
                seg,
                judgement,
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
            combined_audio_parts = []
            combined_scene_elements = []
            sub_segment_subtitle_texts = []  # list of list[str]
            sub_segment_estimated_durations = []
            sub_idx = 0
            SPEECH_CPS = 3.5  # approximate Chinese chars per second

            for story_i, s in enumerate(story_scan_segs):
                card_narrations = s.meta.get("card_narrations", [])
                if not card_narrations:
                    card_audio = (s.audio_text or "").strip()
                    if not card_audio:
                        continue
                    texts = [card_audio]
                    combined_audio_parts.append(card_audio)
                    sub_segment_subtitle_texts.append(texts)
                    sub_segment_estimated_durations.append(
                        sum(max(2.0, len(t) / SPEECH_CPS) for t in texts)
                    )
                    for elem in s.scene_elements:
                        elem.sub_segment_index = sub_idx
                        if elem.element_type == "event_card":
                            elem.props["display_index"] = story_i
                            elem.props["story_count"] = len(story_scan_segs)
                        elem.props["subtitle_texts"] = texts
                        combined_scene_elements.append(elem)
                    sub_idx += 1
                    continue

                for card in card_narrations:
                    raw_texts = card.get("subtitle_texts", []) or []
                    texts = [t.strip() for t in raw_texts if t and t.strip()]
                    if not texts:
                        continue
                    card_type = card.get("card_type", "")

                    for t in texts:
                        combined_audio_parts.append(t)
                    sub_segment_subtitle_texts.append(texts)
                    sub_segment_estimated_durations.append(
                        sum(max(2.0, len(t) / SPEECH_CPS) for t in texts)
                    )

                    matched = False
                    for elem in s.scene_elements:
                        if elem.element_type == card_type and elem.sub_segment_index is None:
                            elem.sub_segment_index = sub_idx
                            if elem.element_type == "event_card":
                                elem.props["display_index"] = story_i
                                elem.props["story_count"] = len(story_scan_segs)
                            elem.props["subtitle_texts"] = texts
                            combined_scene_elements.append(elem)
                            matched = True
                            break

                    if not matched:
                        self.logger.debug(
                            f"card_narration type '{card_type}' has no matching scene_element in story {story_i}"
                        )

                    sub_idx += 1

            combined_audio = " ".join(combined_audio_parts)
            total_duration = sum(sub_segment_estimated_durations)

            story_scan_seg = ScriptSegment(
                segment_type="story_scan",
                audio_text=combined_audio,
                estimated_duration=total_duration,
                emotion="upbeat",
                scene_elements=combined_scene_elements,
                meta={
                    "sub_segment_subtitle_texts": sub_segment_subtitle_texts,
                    "sub_segment_estimated_durations": sub_segment_estimated_durations,
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
            # Fallback: if all selected comments lack source_id, keep original LLM ids
            if not props["selected_comment_ids"] and combined_ids:
                props["selected_comment_ids"] = [str(cid) for cid in combined_ids[:3]]
            elem.props = props

    @staticmethod
    def _normalize_atmosphere_card(segment: ScriptSegment, judgement: dict) -> None:
        """Inject debate_focus and stance_distribution from comment judgement into atmosphere_card props."""
        debate_focus = judgement.get("debate_focus") or []
        stance_distribution = judgement.get("stance_distribution") or {}
        if not debate_focus and not stance_distribution:
            return
        for elem in segment.scene_elements:
            if elem.element_type != "atmosphere_card":
                continue
            props = dict(elem.props or {})
            if debate_focus:
                props["debate_focus"] = debate_focus
            if stance_distribution:
                props["stance_distribution"] = stance_distribution
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
        _save_script(script, date, logger=self.logger)

    def generate_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> str:
        return _generate_brief_transcript(script, date, content)

    def save_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> Path:
        return _save_transcript(script, date, content, logger=self.logger)

    def load_script(self, date: str) -> Script:
        return _load_script(date)

    def _validate_cache_metadata(self, script: Script, content) -> bool:
        """Check cached script has timing metadata needed for card/cue alignment.

        Returns False if the cache is stale and should be regenerated.
        """
        story_scan = next(
            (s for s in script.segments if s.segment_type == "story_scan"), None
        )
        if story_scan is None:
            return True  # No story_scan to validate

        # Must have per-card subtitle_texts for per-subtitle TTS timing
        if not story_scan.meta.get("sub_segment_subtitle_texts"):
            return False

        # Milestone 2: story cards need editable fields for productized narrative.
        # Fields may come from event_card props or ContentItem (enrichment).
        for elem in story_scan.scene_elements:
            if elem.element_type == "event_card":
                si = elem.props.get("story_index")
                item = content.items[si] if si is not None and si < len(content.items) else None
                has_angle = elem.props.get("editor_angle") or (item.editor_angle if item else None)
                has_dek = elem.props.get("dek") or elem.props.get("event_summary") or (item.dek if item else None)
                has_kp = elem.props.get("key_points") or (item.key_points if item else None)
                if not has_angle:
                    return False
                if not has_dek:
                    return False
                if not has_kp:
                    return False

        # Scene elements must know their sub-segment index
        for elem in story_scan.scene_elements:
            if elem.sub_segment_index is None:
                return False

        return True
