"""Script composition: assemble Script from story specs."""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.core.interfaces import LLMProvider
from src.core.models import (
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
    SelectionResult,
)
from src.pipeline.comment import (
    comment_judgement_key,
    load_comment_judgements,
)
from src.pipeline.content_io import ContentPreparer
from src.pipeline.script.cards import (
    coerce_card_narrations_for_mode,
    extract_subtitle_texts,
    normalize_atmosphere_card,
    normalize_story_cards,
    split_long_subtitle,
)
from src.pipeline.script.io import (
    load_script as _load_script,
    save_script as _save_script,
)
from src.pipeline.script.templates import (
    build_highlight_entries,
    generate_fixed_closing,
    generate_fixed_opening,
    highlight_audio_text,
    story_angle_from_segment,
)
from src.utils.logger import setup_logger


SPEECH_CPS = 3.5


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
    def _prompt_for_presentation(mode: str) -> str:
        return "prompts/story_script.md"

    @staticmethod
    def _expected_card_types(mode: str) -> list[str]:
        return ["event_card", "atmosphere_card"]

    def _calculate_max_workers(self, story_indices: list[int]) -> int:
        max_workers = int(self.config.get("llm", {}).get("max_workers", 1) or 1)
        return max(1, min(max_workers, len(story_indices) or 1))

    @staticmethod
    def _normalize_story_specs(story_specs: list[dict]) -> list[dict]:
        specs = []
        for entry in story_specs:
            story_index = entry.get("story_index")
            if story_index is None:
                continue
            specs.append(
                {
                    "story_index": int(story_index),
                    "coverage_tier": entry.get("coverage_tier", "focus"),
                    "presentation_mode": entry.get("presentation_mode", "deep"),
                    "section": entry.get("section", ""),
                }
            )
        return specs

    def _generate_story_scan_segments(
        self,
        content: ContentPackage,
        story_indices: list,
        date: str,
    ) -> list[ScriptSegment]:
        story_specs = self._normalize_story_specs(story_indices)
        if not story_specs:
            return []

        comment_judgements = load_comment_judgements(date)
        story_indices = [spec["story_index"] for spec in story_specs]
        max_workers = self._calculate_max_workers(story_indices)

        def _generate_single(spec: dict) -> ScriptSegment:
            story_idx = spec["story_index"]
            item = content.items[story_idx]
            judgement = comment_judgements.get(comment_judgement_key(item), {})
            mode = spec.get("presentation_mode", "deep")
            segment = self.llm_provider.generate_single_story_segment(
                content=content,
                story_index=story_idx,
                segment_type="story_scan_item",
                prompt_template_path=self._prompt_for_presentation(mode),
                date=date,
                comments_data=judgement or None,
                expected_card_types=self._expected_card_types(mode),
            )
            segment.meta["coverage_tier"] = spec.get("coverage_tier", "focus")
            segment.meta["presentation_mode"] = spec.get("presentation_mode", "deep")
            segment.meta["section"] = spec.get("section", "")
            segment.meta["story_index"] = story_idx
            return segment

        if max_workers == 1 or len(story_indices) <= 1:
            segments_by_index = {}
            for i, spec in enumerate(story_specs):
                idx = spec["story_index"]
                title = (content.items[idx].title or "")[:40]
                self.logger.info(
                    f"  Script: story {i + 1}/{len(story_specs)} — {title}"
                )
                segments_by_index[idx] = _generate_single(spec)
        else:
            self.logger.info(
                f"Generating {len(story_indices)} story scans with {max_workers} LLM workers"
            )
            segments_by_index = {}
            completed = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_generate_single, spec): spec["story_index"]
                    for spec in story_specs
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    segments_by_index[idx] = future.result()
                    completed += 1
                    self.logger.info(f"  Script: {completed}/{len(story_specs)} done")

        ordered = [
            segments_by_index[idx] for idx in story_indices if idx in segments_by_index
        ]

        for story_idx, seg in zip(story_indices, ordered):
            spec = next(
                (s for s in story_specs if s["story_index"] == story_idx),
                {"presentation_mode": "deep"},
            )
            coerce_card_narrations_for_mode(seg, spec.get("presentation_mode", "deep"))
            judgement = comment_judgements.get(
                comment_judgement_key(content.items[story_idx]), {}
            )
            normalize_atmosphere_card(seg, content.items[story_idx], judgement)
            normalize_story_cards(seg, content.items[story_idx], judgement)

        return ordered

    def _match_card_to_element(
        self,
        scene_elements: list[SceneElement],
        card_type: str,
        sub_idx: int,
        story_i: int,
        total_stories: int,
        subtitle_texts: list[str],
    ) -> Optional[SceneElement]:
        for elem in scene_elements:
            if elem.element_type == card_type and elem.sub_segment_index is None:
                elem.sub_segment_index = sub_idx
                if elem.element_type in {
                    "event_card",
                }:
                    elem.props["display_index"] = story_i
                    elem.props["story_count"] = total_stories
                elem.props["subtitle_texts"] = subtitle_texts
                return elem
        return None

    def _process_story_narrations(
        self,
        segment: ScriptSegment,
        story_i: int,
        total_stories: int,
        start_sub_idx: int,
    ) -> tuple[list[str], list[SceneElement], list[list[str]], list[float]]:
        audio_parts: list[str] = []
        scene_elems: list[SceneElement] = []
        subtitle_texts_list: list[list[str]] = []
        durations: list[float] = []

        card_narrations = segment.meta.get("card_narrations", [])

        if not card_narrations:
            card_audio = (segment.audio_text or "").strip()
            if not card_audio:
                return audio_parts, scene_elems, subtitle_texts_list, durations
            texts = [card_audio]
            audio_parts.append(card_audio)
            subtitle_texts_list.append(texts)
            durations.append(sum(max(2.0, len(t) / SPEECH_CPS) for t in texts))
            for elem in segment.scene_elements:
                elem.sub_segment_index = start_sub_idx
                if elem.element_type == "event_card":
                    elem.props["display_index"] = story_i
                    elem.props["story_count"] = total_stories
                elem.props["subtitle_texts"] = texts
                scene_elems.append(elem)
            return audio_parts, scene_elems, subtitle_texts_list, durations

        sub_idx = start_sub_idx
        for card in card_narrations:
            texts = extract_subtitle_texts(card)
            if not texts:
                continue
            card_type = card.get("card_type", "")

            audio_parts.extend(texts)
            subtitle_texts_list.append(texts)
            durations.append(sum(max(2.0, len(t) / SPEECH_CPS) for t in texts))

            matched = self._match_card_to_element(
                segment.scene_elements,
                card_type,
                sub_idx,
                story_i,
                total_stories,
                texts,
            )
            if matched:
                scene_elems.append(matched)
            else:
                self.logger.debug(
                    f"card_narration type '{card_type}' has no matching scene_element in story {story_i}"
                )

            sub_idx += 1

        return audio_parts, scene_elems, subtitle_texts_list, durations

    def _compose_story_scan_segment(
        self,
        story_scan_segs: list[ScriptSegment],
    ) -> ScriptSegment:
        combined_audio_parts: list[str] = []
        combined_scene_elements: list[SceneElement] = []
        sub_segment_subtitle_texts: list[list[str]] = []
        sub_segment_estimated_durations: list[float] = []

        story_gap = float(self.config.get("timing", {}).get("story_gap", 0.0))
        num_stories = len(story_scan_segs)

        sub_idx = 0
        story_i = 0
        while story_i < num_stories:
            seg = story_scan_segs[story_i]
            audio_parts, scene_elems, subtitle_texts, durations = (
                self._process_story_narrations(seg, story_i, num_stories, sub_idx)
            )
            story_i += 1
            combined_audio_parts.extend(audio_parts)
            combined_scene_elements.extend(scene_elems)
            sub_segment_subtitle_texts.extend(subtitle_texts)
            sub_segment_estimated_durations.extend(durations)
            sub_idx += len(subtitle_texts)

            if story_gap > 0 and story_i < num_stories:
                combined_scene_elements.append(
                    SceneElement(
                        element_type="story_gap",
                        start_time=0.0,
                        end_time=story_gap,
                        props={"gap_duration": story_gap},
                    )
                )
                sub_segment_estimated_durations.append(story_gap)

        return ScriptSegment(
            segment_type="story_scan",
            audio_text=" ".join(combined_audio_parts),
            duration=sum(sub_segment_estimated_durations),
            scene_elements=combined_scene_elements,
            meta={
                "sub_segment_subtitle_texts": sub_segment_subtitle_texts,
                "sub_segment_estimated_durations": sub_segment_estimated_durations,
            },
        )

    def _build_story_specs(self, content: ContentPackage) -> list[dict]:
        pipeline_cfg = self.config.get("pipeline", {})
        total = int(pipeline_cfg.get("target_story_count", 3) or 3)
        total = min(total, len(content.items))

        specs: list[dict] = []
        max_count = total
        for i in range(max_count):
            tier, mode, section = "focus", "deep", "重点观察"
            specs.append(
                {
                    "story_index": i,
                    "coverage_tier": tier,
                    "presentation_mode": mode,
                    "section": section,
                }
            )
        return specs

    def _generate_script_split(
        self, content: ContentPackage, selection: SelectionResult, date: str
    ) -> Script:
        segments: list[ScriptSegment] = []

        story_indices = [
            bi for bi in selection.brief_items if bi.get("story_index") is not None
        ]
        story_scan_segs = self._generate_story_scan_segments(
            content, story_indices, date
        )

        highlight_entries = build_highlight_entries(selection, content, story_scan_segs)
        segments.append(
            generate_fixed_opening(
                date,
                selection,
                content,
                story_scan_segs,
                highlight_entries=highlight_entries,
            )
        )

        if not story_scan_segs:
            self.logger.info(
                f"WARNING: No story_scan segments generated for {len(content.items)} "
                f"content items. Video will have no news content in the middle."
            )
        else:
            segments.append(self._compose_story_scan_segment(story_scan_segs))

        segments.append(generate_fixed_closing(date, highlight_entries))

        return Script(
            title="HN每日观察",
            description=f"每日快讯 - {date}",
            tags=[],
            segments=segments,
        )

    def write(self, content: ContentPackage) -> Script:
        t_total = time.monotonic()

        script_path = Path(f"data/{content.date}/script.json")
        if script_path.exists():
            self.logger.info(f"Found existing {script_path}, loading...")
            script = self.load_script(content.date)
            elapsed = time.monotonic() - t_total
            self.logger.info(f"Script loaded from cache in {elapsed:.1f}s")
            return script

        self.logger.info(f"Input: {len(content.items)} stories, date={content.date}")

        brief_items = self._build_story_specs(content)
        selection = SelectionResult(
            brief_items=brief_items,
            raw_json=json.dumps({"brief_items": brief_items}, ensure_ascii=False),
        )

        self.logger.info(f"Selection: {len(brief_items)} stories by score ranking")
        self.logger.info("Round 2: Script generation (split mode)")
        script = self._generate_script_split(
            content=content, selection=selection, date=content.date
        )

        elapsed = time.monotonic() - t_total
        self.logger.info("=" * 60)
        self.logger.info(f"Pipeline complete in {elapsed:.1f}s")
        self.logger.info("=" * 60)

        return script

    def save_script(self, script: Script, date: str) -> None:
        _save_script(script, date, logger=self.logger)

    def load_script(self, date: str) -> Script:
        return _load_script(date)

    # Backward-compat static method aliases (extracted to script/cards.py)
    _normalize_atmosphere_card = staticmethod(normalize_atmosphere_card)
    _normalize_story_cards = staticmethod(normalize_story_cards)
    _coerce_card_narrations_for_mode = staticmethod(coerce_card_narrations_for_mode)
    _extract_subtitle_texts = staticmethod(extract_subtitle_texts)
    _split_long_subtitle = staticmethod(split_long_subtitle)

    # Backward-compat method aliases (extracted to script/templates.py)
    _generate_fixed_opening = staticmethod(generate_fixed_opening)
    _generate_fixed_closing = staticmethod(generate_fixed_closing)
    _build_highlight_entries = staticmethod(build_highlight_entries)
    _story_angle_from_segment = staticmethod(story_angle_from_segment)
    _highlight_audio_text = staticmethod(highlight_audio_text)
