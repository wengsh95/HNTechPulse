import json
import time
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from src.core.models import Script, ScriptSegment, ContentPackage, ContentItem, SelectionResult
from src.core.interfaces import LLMProvider
from src.pipeline.content_preparer import ContentPreparer
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

    def _generate_fixed_opening(self, date: str) -> ScriptSegment:
        """生成每日快讯开场"""
        from datetime import datetime
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_display = date_obj.strftime("%Y年%m月%d日")
        except (ValueError, TypeError):
            date_display = date

        audio_text = f"大家好，我是小P，今天是{date_display}。来看看今天的Hacker News热门。"
        duration = 7

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
                        "stats": ""
                    }
                )
            ],
            cues=[
                Cue(text=audio_text, start_time=0.0, end_time=float(duration))
            ],
            meta={}
        )

    def _generate_fixed_closing(self) -> ScriptSegment:
        """生成每日快讯结尾"""
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

    def _generate_dashboard_segment(self, selection: SelectionResult, content: ContentPackage) -> ScriptSegment:
        """生成 dashboard 片段"""
        entries = []
        for i, bi in enumerate(selection.brief_items):
            story_idx = bi.get("story_index")
            if story_idx is not None and story_idx < len(content.items):
                item = content.items[story_idx]
                entries.append({
                    "rank": i + 1,
                    "story_index": story_idx,
                    "original_title": item.title,
                    "title_translation": item.title_cn,
                    "score": item.score,
                    "comment_count": item.comment_count,
                })

        return ScriptSegment(
            segment_type="dashboard",
            audio_text="来看看今天的热门榜单。",
            estimated_duration=10,
            emotion="neutral",
            scene_elements=[
                SceneElement(
                    element_type="dashboard_card",
                    start_time=0.0,
                    end_time=10.0,
                    props={"entries": entries}
                )
            ],
            cues=[
                Cue(text="来看看今天的热门榜单。", start_time=0.0, end_time=10.0)
            ],
            meta={"dashboard": {"entries": entries}}
        )

    def _generate_script_split(self, content: ContentPackage, selection: SelectionResult, date: str) -> Script:
        """生成每日快讯脚本（拆分模式）"""

        segments = []

        # 固定开场
        segments.append(self._generate_fixed_opening(date))

        # Dashboard
        segments.append(self._generate_dashboard_segment(selection, content))

        # Story scan
        story_scan_segs = []
        all_brief_items_data = []
        for bi in selection.brief_items:
            story_idx = bi.get("story_index")
            if story_idx is None:
                continue
            seg = self.llm_provider.generate_single_story_segment(
                content=content,
                story_index=story_idx,
                segment_type="story_scan_item",
                prompt_template_path="prompts/single_story_scan.md",
                date=date,
                comments_data=None
            )
            story_scan_segs.append(seg)
            bi_data = {
                "story_index": story_idx,
                "event_summary": seg.meta.get("event_summary", ""),
                "viewpoints": seg.meta.get("viewpoints", []),
            }
            all_brief_items_data.append(bi_data)

        if not story_scan_segs:
            self.logger.info(
                f"WARNING: No story_scan segments generated for {len(content.items)} "
                f"content items. Video will have no news content in the middle."
            )
        else:
            combined_audio = ""
            combined_scene_elements = []
            sub_segment_char_ranges = []  # [(start, end), ...] char offsets in combined_audio
            for i, s in enumerate(story_scan_segs):
                char_start = len(combined_audio)
                if combined_audio:
                    combined_audio += " "
                combined_audio += s.audio_text
                char_end = len(combined_audio)
                sub_segment_char_ranges.append((char_start, char_end))
                for elem in s.scene_elements:
                    elem.sub_segment_index = i
                    combined_scene_elements.append(elem)
            total_duration = sum(s.estimated_duration for s in story_scan_segs)

            story_scan_seg = ScriptSegment(
                segment_type="story_scan",
                audio_text=combined_audio,
                estimated_duration=total_duration,
                emotion="upbeat",
                scene_elements=combined_scene_elements,
                meta={
                    "brief_items": all_brief_items_data,
                    "sub_segment_estimated_durations": [s.estimated_duration for s in story_scan_segs],
                    "sub_segment_char_ranges": sub_segment_char_ranges,
                },
            )
            segments.append(story_scan_seg)

        # 固定结尾
        segments.append(self._generate_fixed_closing())

        return Script(
            title="HN TechPulse 每日快讯",
            description=f"每日快讯 - {date}",
            tags=[],
            segments=segments)

    def write(self, content: ContentPackage) -> Script:
        t_total = time.monotonic()

        # Script checkpoint: if script.json already exists, skip all LLM work.
        script_path = Path(f"data/{content.date}/script.json")
        if script_path.exists():
            self.logger.info(f"Found existing {script_path}, loading...")
            script = self.load_script(content.date)
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
                    comments_str = f" · {comments} comments" if comments else ""
                    if title_cn:
                        lines.append(f"{rank}. **{title}** / {title_cn}{score_str}{comments_str}")
                    else:
                        lines.append(f"{rank}. **{title}**{score_str}{comments_str}")
            elif content:
                for i, item in enumerate(content.items[:10], 1):
                    score_str = f" ▲ {item.score}" if item.score else ""
                    comments_str = f" · {item.comment_count} comments" if item.comment_count else ""
                    title_cn = item.title_cn
                    if title_cn:
                        lines.append(f"{i}. **{item.title}** / {title_cn}{score_str}{comments_str}")
                    else:
                        lines.append(f"{i}. **{item.title}**{score_str}{comments_str}")
            lines.append("")

        # Story scan (逐条速览)
        if scan_segment:
            brief_items = scan_segment.meta.get("brief_items", []) if scan_segment.meta else []
            # 按 score 降序排列，确保展示顺序与 HN 热度排名一致
            if content and brief_items:
                brief_items = sorted(
                    brief_items,
                    key=lambda bi: (
                        content.items[bi["story_index"]].score or 0
                        if 0 <= bi.get("story_index", -1) < len(content.items)
                        else 0
                    ),
                    reverse=True,
                )

            lines.append("---")
            lines.append("")
            lines.append("## 逐条速览")
            lines.append("")
            lines.append(scan_segment.audio_text)
            lines.append("")

            if brief_items:
                for i, bi in enumerate(brief_items, 1):
                    event_summary = bi.get("event_summary", "") or bi.get("one_liner", "")
                    viewpoints = bi.get("viewpoints", [])

                    lines.append(f"### {i}. {event_summary}")
                    if viewpoints:
                        for vp in viewpoints:
                            stance = vp.get("stance", "")
                            summary = vp.get("summary", "")
                            stance_str = f"[{stance}] " if stance else ""
                            lines.append(f"- {stance_str}{summary}")
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
