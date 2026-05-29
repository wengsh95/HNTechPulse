import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.core.models import (
    Script,
    ScriptSegment,
    ContentPackage,
    ContentItem,
    SelectionResult,
)
from src.core.interfaces import LLMProvider
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.comment_judgement import (
    candidate_ids_for_story,
    comment_judgement_key,
    load_comment_judgements,
)
from src.pipeline.comment_selection import (
    classify_comment_stance,
    select_quote_comments,
)
from src.pipeline.script_io import (
    save_script as _save_script,
    load_script as _load_script,
)
from src.utils.logger import setup_logger
from src.core.models import SceneElement


CHINESE_ORDINALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
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
    def _story_angle_from_segment(segment: ScriptSegment, item=None) -> dict:
        """Extract the product-facing angle fields from an LLM story segment."""
        event_elem = next(
            (
                elem
                for elem in segment.scene_elements
                if elem.element_type == "event_card"
            ),
            None,
        )
        props = event_elem.props if event_elem else {}
        return {
            "editor_angle": props.get("editor_angle")
            or (item.editor_angle if item else None)
            or "",
            "dek": props.get("dek") or (item.dek if item else None) or "",
            "key_points": props.get("key_points")
            or (item.key_points if item else None)
            or [],
            "event_summary": props.get("event_summary")
            or (item.dek if item else None)
            or "",
            "why_it_matters": props.get("why_it_matters")
            or (item.why_it_matters if item else None)
            or "",
            "category": props.get("category")
            or (item.category if item else None)
            or "",
            "keywords": props.get("keywords")
            or (item.keywords if item else None)
            or [],
        }

    @classmethod
    def _highlight_audio_text(cls, entries: list[dict]) -> str:
        """Summarize the lineup for listeners who are not watching the screen."""
        labels = []
        for idx, entry in enumerate(entries[:3]):
            title = (
                entry.get("title_translation")
                or entry.get("editor_angle")
                or entry.get("original_title")
                or ""
            )
            title = str(title).strip()
            if len(title) > 18:
                title = title[:18].rstrip("，。！？；：,.!?;:") + "…"
            ordinal = (
                CHINESE_ORDINALS[idx] if idx < len(CHINESE_ORDINALS) else str(idx + 1)
            )
            labels.append(f"第{ordinal}，{title}" if title else f"第{ordinal}条")
        if not labels:
            return "来看今天的三个技术信号，我们一条条听。"
        return f"今天看{len(labels)}条：" + "；".join(labels) + "。我们一条条听。"

    def _generate_fixed_opening(
        self,
        date: str,
        selection: Optional[SelectionResult] = None,
        content: Optional[ContentPackage] = None,
        story_scan_segs: Optional[list[ScriptSegment]] = None,
        highlight_entries: Optional[list[dict]] = None,
    ) -> ScriptSegment:
        """Generate a short positioning line before the first story."""
        from datetime import datetime

        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_display = date_obj.strftime("%Y年%m月%d日")
        except (ValueError, TypeError):
            date_display = date

        entries = highlight_entries or []
        focus_count = len([e for e in entries if e.get("coverage_tier") == "focus"])
        standard_count = len(
            [e for e in entries if e.get("coverage_tier") == "standard"]
        )
        quick_count = len([e for e in entries if e.get("coverage_tier") == "quick"])
        if len(entries) > 3:
            audio_text = (
                f"早上好，这里是 HN每日观察。今天选了{len(entries)}条讨论，"
                f"{focus_count}条重点，{standard_count}条速读，{quick_count}条快扫。"
            )
            duration = 8
        else:
            audio_text = "早上好，这里是 HN每日观察，带你看昨天HN发生了什么。"
            duration = 5

        # Collect headline titles from top-3 to exclude as keywords (would duplicate visible text)
        top3_titles: list[str] = []
        if story_scan_segs:
            for seg in story_scan_segs[:3]:
                for elem in seg.scene_elements:
                    if elem.element_type == "event_card":
                        title = (
                            elem.props.get("editor_angle")
                            or elem.props.get("title_cn")
                            or ""
                        )
                        if title:
                            top3_titles.append(str(title))
                        break

        keyword_counts: dict[str, int] = {}
        for entry in entries:
            for kw in entry.get("keywords") or []:
                token = str(kw).strip()
                if not token:
                    continue
                if any(token in t or t in token for t in top3_titles):
                    continue
                keyword_counts[token] = keyword_counts.get(token, 0) + 1
        keywords: list[str] = [
            kw for kw, _ in sorted(keyword_counts.items(), key=lambda x: (-x[1], x[0]))
        ][:3]
        # Fallback: category labels of remaining (non-top3) entries
        if len(keywords) < 3:
            seen = set(keywords)
            for entry in entries[3:]:
                cat = str(entry.get("category") or "").strip()
                if cat and cat not in seen:
                    keywords.append(cat)
                    seen.add(cat)
                    if len(keywords) >= 3:
                        break

        return ScriptSegment(
            segment_type="opening",
            audio_text=audio_text,
            duration=duration,
            scene_elements=[
                SceneElement(
                    element_type="cover_card",
                    start_time=0.0,
                    end_time=duration,
                    props={
                        "headline": "每日技术速览",
                        "subtitle": date_display,
                        "keywords": keywords[:3],
                        "lineup_entries": entries,
                        "section_counts": {
                            "focus": focus_count,
                            "standard": standard_count,
                            "quick": quick_count,
                        },
                    }
                    | (
                        {
                            "highlight_entries": highlight_entries[:3],
                            "focus_count": focus_count
                            or min(3, len(highlight_entries)),
                        }
                        if highlight_entries
                        else {}
                    ),
                )
            ],
            meta={"highlights": {"entries": entries}} if highlight_entries else {},
        )

    @staticmethod
    def _closing_keywords(highlight_entries: Optional[list[dict]] = None) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()

        def add_keyword(value) -> None:
            if not value:
                return
            text = str(value).strip()
            if not text or text in seen:
                return
            seen.add(text)
            keywords.append(text)

        for entry in highlight_entries or []:
            add_keyword(entry.get("category"))
            for keyword in entry.get("keywords") or []:
                add_keyword(keyword)
            if len(keywords) >= 3:
                break

        return (keywords or ["Agents", "Infra", "Developer Tools"])[:3]

    @staticmethod
    def _closing_summary_items(
        highlight_entries: Optional[list[dict]] = None,
    ) -> list[dict]:
        items: list[dict] = []
        for entry in (highlight_entries or [])[:3]:
            title = (
                entry.get("editor_angle")
                or entry.get("title_translation")
                or entry.get("original_title")
                or ""
            )
            note = entry.get("why_it_matters") or ""
            category = entry.get("category") or "观察"
            if not title and not note:
                continue
            items.append(
                {
                    "category": str(category),
                    "title": str(title),
                    "note": str(note),
                }
            )

        if items:
            return items

        return [
            {
                "category": "AI",
                "title": "AI 正从产品功能，变成开发工作流的底层能力。",
                "note": "继续关注工具链、成本结构与真实生产力提升。",
            },
            {
                "category": "Infra",
                "title": "底层基础设施仍是社区判断技术价值的核心坐标。",
                "note": "性能、可控性和维护成本比发布声量更重要。",
            },
        ]

    @staticmethod
    def _closing_totals(highlight_entries: Optional[list[dict]] = None) -> dict:
        entries = highlight_entries or []
        story_count = len(entries)
        score_total = sum(
            int(entry.get("score") or 0)
            for entry in entries
            if str(entry.get("score") or "").isdigit()
        )
        comment_total = sum(
            int(entry.get("comment_count") or 0)
            for entry in entries
            if str(entry.get("comment_count") or "").isdigit()
        )
        return {
            "story_count": story_count,
            "score_total": score_total,
            "comment_total": comment_total,
        }

    @staticmethod
    def _closing_takeaways(highlight_entries: Optional[list[dict]] = None) -> list[str]:
        takeaways: list[str] = []
        for entry in (highlight_entries or [])[:3]:
            text = (
                entry.get("why_it_matters")
                or entry.get("editor_angle")
                or entry.get("title_translation")
                or ""
            )
            text = str(text).strip()
            if not text:
                continue
            if len(text) > 34:
                text = text[:34].rstrip("，。！？；：,.!?;:") + "…"
            takeaways.append(text)
        return takeaways[:3]

    def _generate_fixed_closing(
        self, date: str, highlight_entries: Optional[list[dict]] = None
    ) -> ScriptSegment:
        """生成每日快讯结尾"""
        from datetime import datetime

        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            weekday = date_obj.weekday()
        except (ValueError, TypeError):
            weekday = None

        if weekday in {4, 5}:
            audio_text = "今天的 HN 速览就到这里，周末继续留意那些真正值得追的问题。"
        else:
            audio_text = "今天的 HN 速览就到这里，我们明天继续看哪些讨论值得停一下。"
        duration = 8
        takeaways = self._closing_takeaways(highlight_entries)
        signal = (
            "今天值得带走的，是这些讨论各自提出的具体问题。"
            if highlight_entries and len(highlight_entries) > 3
            else (
                takeaways[0] if takeaways else "今天的技术讨论，先记住问题，再看答案。"
            )
        )
        keywords = self._closing_keywords(highlight_entries)
        summary_items = self._closing_summary_items(highlight_entries)
        totals = self._closing_totals(highlight_entries)

        return ScriptSegment(
            segment_type="closing",
            audio_text=audio_text,
            duration=duration,
            scene_elements=[
                SceneElement(
                    element_type="closing_card",
                    start_time=0.0,
                    end_time=duration,
                    props={
                        "signal_label": "今日信号",
                        "signal": signal,
                        "keywords_label": "今日关键词",
                        "keywords": keywords,
                        "summary_label": "今日脉络",
                        "summary_items": summary_items,
                        "takeaways": takeaways,
                        "closing_mode": "takeaways",
                        "totals": totals,
                    },
                )
            ],
            meta={},
        )

    def _build_highlight_entries(
        self,
        selection: SelectionResult,
        content: ContentPackage,
        story_scan_segs: Optional[list[ScriptSegment]] = None,
    ) -> list[dict]:
        """Build the opening highlight list from selected stories."""
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
            item = (
                content.items[story_index]
                if story_index is not None and story_index < len(content.items)
                else None
            )
            angle = self._story_angle_from_segment(seg, item=item)
            if story_index is not None:
                angle_by_story[int(story_index)] = angle

        for i, bi in enumerate(selection.brief_items):
            story_idx = bi.get("story_index")
            if story_idx is not None and story_idx < len(content.items):
                item = content.items[story_idx]
                angle = angle_by_story.get(story_idx, {})
                entries.append(
                    {
                        "rank": i + 1,
                        "story_index": story_idx,
                        "original_title": item.title,
                        "title_translation": item.title_cn,
                        "editor_angle": angle.get("editor_angle")
                        or angle.get("dek")
                        or angle.get("event_summary")
                        or item.title_cn
                        or item.title,
                        "why_it_matters": angle.get("why_it_matters") or "",
                        "category": angle.get("category") or "",
                        "keywords": angle.get("keywords") or [],
                        "score": item.score,
                        "comment_count": item.comment_count,
                        "coverage_tier": bi.get("coverage_tier", "focus"),
                        "presentation_mode": bi.get("presentation_mode", "deep"),
                        "section": bi.get("section", ""),
                    }
                )

        return entries

    @staticmethod
    def _extract_story_specs(selection: SelectionResult) -> list[dict]:
        return [bi for bi in selection.brief_items if bi.get("story_index") is not None]

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

    @staticmethod
    def _prompt_for_presentation(mode: str) -> str:
        if mode == "quick":
            return "prompts/story_script_quick.md"
        if mode == "standard":
            return "prompts/story_script_standard.md"
        return "prompts/story_script.md"

    @staticmethod
    def _expected_card_types(mode: str) -> list[str]:
        if mode == "quick":
            return ["quick_item_card"]
        if mode == "standard":
            return ["story_compact_card"]
        return ["event_card", "atmosphere_card"]

    def _coerce_card_narrations_for_mode(
        self, segment: ScriptSegment, mode: str
    ) -> None:
        """Keep LLM output within the configured tier shape."""
        expected = self._expected_card_types(mode)
        card_narrations = segment.meta.get("card_narrations", []) or []
        filtered = [
            card for card in card_narrations if card.get("card_type") in expected
        ]
        if filtered:
            segment.meta["card_narrations"] = filtered

        segment.scene_elements = [
            elem for elem in segment.scene_elements if elem.element_type in expected
        ]
        story_index = segment.meta.get("story_index")
        for elem in segment.scene_elements:
            if story_index is not None:
                break
            if elem.props.get("story_index") is not None:
                story_index = elem.props.get("story_index")
                break
        if story_index is None:
            story_index = segment.meta.get("story_index", 0)

        existing = set()
        for elem in segment.scene_elements:
            existing.add(elem.element_type)
            props = dict(elem.props or {})
            props["story_index"] = story_index
            elem.props = props

        for card_type in expected:
            if card_type not in existing:
                segment.scene_elements.append(
                    SceneElement(
                        element_type=card_type,
                        start_time=0.0,
                        end_time=5.0,
                        props={"story_index": story_index},
                    )
                )

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
            segments_by_index = {
                spec["story_index"]: _generate_single(spec) for spec in story_specs
            }
        else:
            self.logger.info(
                f"Generating {len(story_indices)} story scans with {max_workers} LLM workers"
            )
            segments_by_index = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_generate_single, spec): spec["story_index"]
                    for spec in story_specs
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    segments_by_index[idx] = future.result()

        ordered = [
            segments_by_index[idx] for idx in story_indices if idx in segments_by_index
        ]

        for story_idx, seg in zip(story_indices, ordered):
            spec = next(
                (s for s in story_specs if s["story_index"] == story_idx),
                {"presentation_mode": "deep"},
            )
            self._coerce_card_narrations_for_mode(
                seg, spec.get("presentation_mode", "deep")
            )
            judgement = comment_judgements.get(
                comment_judgement_key(content.items[story_idx]), {}
            )
            self._normalize_atmosphere_card(seg, content.items[story_idx], judgement)
            self._normalize_story_cards(seg, content.items[story_idx], judgement)

        return ordered

    @staticmethod
    def _extract_subtitle_texts(card: dict) -> list[str]:
        raw_texts = card.get("subtitle_texts", []) or []
        return [
            piece
            for t in raw_texts
            if t and t.strip()
            for piece in ScriptWriter._split_long_subtitle(t.strip())
        ]

    @staticmethod
    def _split_long_subtitle(
        text: str, max_cjk: int = 36, max_chars: int = 70
    ) -> list[str]:
        """Split a single subtitle into 1-2 cues when it exceeds the readable width.

        CJK characters count fully; ASCII counts half. Splits on Chinese punctuation
        nearest the midpoint. Returns [text] unchanged when within budget or no split
        point is found.
        """
        cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
        ascii_count = len(text) - cjk_count
        weight = cjk_count + ascii_count / 2
        if weight <= max_cjk and len(text) <= max_chars:
            return [text]

        breakers = "，。；：、!?！？,;"
        midpoint = len(text) // 2
        best_idx = -1
        best_dist = len(text)
        for i, ch in enumerate(text):
            if ch in breakers:
                dist = abs(i - midpoint)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
        if best_idx <= 0 or best_idx >= len(text) - 1:
            return [text]
        left = text[: best_idx + 1].rstrip(breakers + " ").strip()
        right = text[best_idx + 1 :].lstrip(breakers + " ").strip()
        if not left or not right:
            return [text]
        return [left, right]

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
                    "story_compact_card",
                    "quick_item_card",
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
            texts = self._extract_subtitle_texts(card)
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

    @staticmethod
    def _is_quick_segment(segment: ScriptSegment) -> bool:
        return segment.meta.get("presentation_mode") == "quick"

    @staticmethod
    def _quick_roundup_item_from_segment(
        segment: ScriptSegment, display_index: int
    ) -> dict:
        quick_elem = next(
            (
                elem
                for elem in segment.scene_elements
                if elem.element_type == "quick_item_card"
            ),
            None,
        )
        props = dict(quick_elem.props if quick_elem else {})
        story_index = segment.meta.get("story_index", props.get("story_index"))
        return {
            "story_index": story_index,
            "display_index": display_index,
            "source_title": props.get("source_title", ""),
            "display_title": props.get("display_title", ""),
            "quick_label": props.get("quick_label", ""),
            "micro_takeaway": props.get("micro_takeaway", ""),
            "category": props.get("category", ""),
            "keywords": props.get("keywords", []),
        }

    def _process_quick_roundup(
        self,
        quick_segments: list[ScriptSegment],
        start_story_i: int,
        total_stories: int,
        sub_idx: int,
    ) -> tuple[list[str], list[SceneElement], list[list[str]], list[float]]:
        audio_parts: list[str] = []
        subtitle_texts: list[str] = []
        items: list[dict] = []

        for offset, seg in enumerate(quick_segments):
            card_narrations = seg.meta.get("card_narrations", []) or []
            texts: list[str] = []
            for card in card_narrations:
                if card.get("card_type") == "quick_item_card":
                    texts.extend(self._extract_subtitle_texts(card))
            if not texts and seg.audio_text:
                texts = [seg.audio_text.strip()]
            if not texts:
                raise ValueError(
                    "quick_roundup_card requires one subtitle text for every quick story"
                )

            text = texts[0].strip()
            audio_parts.append(text)
            subtitle_texts.append(text)
            items.append(
                self._quick_roundup_item_from_segment(
                    seg, display_index=start_story_i + offset
                )
            )

        duration = sum(max(2.0, len(t) / SPEECH_CPS) for t in subtitle_texts)
        elem = SceneElement(
            element_type="quick_roundup_card",
            start_time=0.0,
            end_time=duration,
            sub_segment_index=sub_idx,
            props={
                "section": "快扫",
                "display_index": start_story_i,
                "story_count": total_stories,
                "items": items,
                "subtitle_texts": subtitle_texts,
            },
        )
        return audio_parts, [elem], [subtitle_texts], [duration]

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
            if self._is_quick_segment(seg):
                quick_segments = []
                start_story_i = story_i
                while story_i < num_stories and self._is_quick_segment(
                    story_scan_segs[story_i]
                ):
                    quick_segments.append(story_scan_segs[story_i])
                    story_i += 1
                audio_parts, scene_elems, subtitle_texts, durations = (
                    self._process_quick_roundup(
                        quick_segments, start_story_i, num_stories, sub_idx
                    )
                )
            else:
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
        total = int(pipeline_cfg.get("target_story_count", 10) or 10)
        total = min(total, len(content.items))
        focus_count = int(pipeline_cfg.get("focus_items", 3) or 3)
        standard_count = int(pipeline_cfg.get("standard_items", 3) or 3)
        quick_count = int(
            pipeline_cfg.get(
                "quick_items", max(0, total - focus_count - standard_count)
            )
            or 0
        )

        specs: list[dict] = []
        max_count = min(total, focus_count + standard_count + quick_count)
        for i in range(max_count):
            if i < focus_count:
                tier, mode, section = "focus", "deep", "重点观察"
            elif i < focus_count + standard_count:
                tier, mode, section = "standard", "standard", "速读"
            else:
                tier, mode, section = "quick", "quick", "快扫"
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

        story_indices = self._extract_story_specs(selection)
        story_scan_segs = self._generate_story_scan_segments(
            content, story_indices, date
        )

        highlight_entries = self._build_highlight_entries(
            selection, content, story_scan_segs
        )
        segments.append(
            self._generate_fixed_opening(
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

        segments.append(self._generate_fixed_closing(date, highlight_entries))

        return Script(
            title="HN每日观察",
            description=f"每日快讯 - {date}",
            tags=[],
            segments=segments,
        )

    @staticmethod
    def _normalize_atmosphere_card(
        segment: ScriptSegment, item: ContentItem, judgement: dict
    ) -> None:
        """Inject debate_focus, stance_distribution, and selected_comment_ids from comment judgement into atmosphere_card props."""
        debate_focus = judgement.get("debate_focus") or []
        stance_distribution = judgement.get("stance_distribution") or {}
        preferred_ids = candidate_ids_for_story(judgement, max_n=12)

        for elem in segment.scene_elements:
            if elem.element_type != "atmosphere_card":
                continue
            props = dict(elem.props or {})
            if debate_focus:
                props["debate_focus"] = debate_focus
            if stance_distribution:
                props["stance_distribution"] = stance_distribution

            # Quote selection (default 2, bumped to 3 only when one stance dominates >=60%
            # and is not yet represented — keeps editorial freedom while avoiding the
            # "top stance missing from quotes" failure mode).
            selected_ids = props.get("selected_comment_ids") or []
            combined_ids = list(selected_ids)
            for comment_id in preferred_ids:
                if comment_id not in combined_ids:
                    combined_ids.append(comment_id)

            comments_by_id = {
                str(c.source_id): c for c in item.comments if c.source_id is not None
            }
            preselected_stances = {
                classify_comment_stance(comments_by_id[str(cid)])
                for cid in combined_ids
                if str(cid) in comments_by_id
            }
            quote_cap = 2
            if stance_distribution:
                dominant_stance, dominant_share = max(
                    stance_distribution.items(), key=lambda x: x[1]
                )
                if dominant_share >= 0.6 and dominant_stance not in preselected_stances:
                    quote_cap = 3

            selected_comments = select_quote_comments(
                item.comments,
                selected_ids=combined_ids,
                judgement=judgement,
                max_n=quote_cap,
            )
            props["selected_comment_ids"] = [
                str(c.source_id) for c in selected_comments if c.source_id is not None
            ]
            if not props["selected_comment_ids"] and combined_ids:
                props["selected_comment_ids"] = [
                    str(cid) for cid in combined_ids[:quote_cap]
                ]

            elem.props = props

    @staticmethod
    def _normalize_story_cards(
        segment: ScriptSegment, item: ContentItem, judgement: dict
    ) -> None:
        """Inject common story metadata into all visual story card variants."""
        for elem in segment.scene_elements:
            if elem.element_type not in {
                "event_card",
                "atmosphere_card",
                "story_compact_card",
                "quick_roundup_card",
            }:
                continue
            props = dict(elem.props or {})
            props.setdefault("source_title", item.title)
            if item.title_cn:
                props.setdefault("title_cn", item.title_cn)
            if item.editor_angle:
                props.setdefault("editor_angle", item.editor_angle)
            if item.key_points:
                props.setdefault("key_points", item.key_points)
            if item.keywords:
                props.setdefault("keywords", item.keywords)
            if item.category:
                props.setdefault("category", item.category)
            if item.why_it_matters:
                props.setdefault("why_it_matters", item.why_it_matters)
            if item.score is not None:
                props.setdefault("score", item.score)
            if item.comment_count is not None:
                props.setdefault("comment_count", item.comment_count)
            if judgement:
                props.setdefault(
                    "discussion_mode", judgement.get("discussion_mode", "")
                )
                props.setdefault(
                    "discussion_summary", judgement.get("discussion_summary", "")
                )
            elem.props = props

    def write(self, content: ContentPackage) -> Script:
        t_total = time.monotonic()

        # Script checkpoint: if script.json already exists, skip all LLM work.
        script_path = Path(f"data/{content.date}/script.json")
        if script_path.exists():
            self.logger.info(f"Found existing {script_path}, loading...")
            script = self.load_script(content.date)
            elapsed = time.monotonic() - t_total
            self.logger.info(f"Script loaded from cache in {elapsed:.1f}s")
            return script

        self.logger.info(f"Input: {len(content.items)} stories, date={content.date}")

        # Build selection from top N stories (already sorted upstream). Programmatic
        # tiers keep the episode structure stable; LLMs only write each local item.
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
