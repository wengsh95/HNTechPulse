import json
import time
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from src.core.models import Script, ScriptSegment, ContentPackage, ContentItem, SelectionResult
from src.core.interfaces import LLMProvider
from src.core.prompts import render_prompt
from src.pipeline.content_preparer import ContentPreparer
from src.utils.logger import setup_logger

SEGMENT_TYPE_LABELS = {
    "opening": "开场",
    "deep_dive": "深度解读",
    "medium_dive": "焦点关注",
    "quick_news": "快讯速览",
    "quick_briefs": "今日快讯",
    "dashboard": "仪表盘",
    "story_scan": "逐条速览",
    "context": "背景",
    "viewpoint_a": "阵营一",
    "viewpoint_b": "阵营二",
    "comment_deep": "评论深挖",
    "synthesis": "洞察",
    "closing": "结尾",
}


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

    def _inject_persona(self, template_text: str, prompts_dir: Path) -> str:
        persona_path = prompts_dir / "persona.md"
        persona = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""
        return render_prompt(template_text, persona=persona)

    def write(self, content: ContentPackage, prompt_template: str, product: str = "full") -> Script:
        t_total = time.monotonic()

        _prompt_path = Path(prompt_template)
        if _prompt_path.exists() and _prompt_path.suffix == ".md":
            prompts_dir = _prompt_path.parent
            script_prompt_text = _prompt_path.read_text(encoding="utf-8")
        else:
            prompts_dir = Path("prompts")
            script_prompt_text = prompt_template

        script_prompt_text = self._inject_persona(script_prompt_text, prompts_dir)

        analyze_prompt_path = prompts_dir / "round1_analyze_story.md"

        # Select decision prompt based on product type
        if product == "daily_brief":
            decision_prompt_path = prompts_dir / "round1_global_decision_brief.md"
        elif product == "deep_dive":
            decision_prompt_path = prompts_dir / "round1_global_decision_deep_dive.md"
        else:
            decision_prompt_path = prompts_dir / "round1_global_decision.md"

        for p, name in [(analyze_prompt_path, "round1_analyze_story.md"),
                        (decision_prompt_path, "round1_global_decision.md")]:
            if not p.exists():
                raise FileNotFoundError(
                    f"Prompt not found: {p}. "
                    f"Expected alongside script_gen.md at prompts/{name}"
                )

        # R2 checkpoint: if script.json already exists, skip R1a/R1b/translate entirely.
        # The translated content.json (if translation ever ran) is on disk already,
        # so downstream steps still see translated titles/comments.
        script_path = Path(f"data/{content.date}/script.json")
        if script_path.exists():
            self.logger.info(f"Found existing {script_path}, loading and skipping R1a/R1b/R2")
            script = self.load_script(content.date)
            elapsed = time.monotonic() - t_total
            self.logger.info(f"Script loaded from cache in {elapsed:.1f}s")
            return script

        analyze_prompt = analyze_prompt_path.read_text(encoding="utf-8")
        decision_prompt = decision_prompt_path.read_text(encoding="utf-8")

        self.logger.info(f"Prompts loaded from {prompts_dir}/")
        self.logger.info(f"Input: {len(content.items)} stories, date={content.date}")
        self.logger.info("Checkpoint recovery enabled: R1a/R1b/R2 cached independently")

        self.logger.info("Round 1: Topic selection + comment filtering")
        selection = self.llm_provider.generate_selection(
            content, analyze_prompt, decision_prompt
        )

        # Translate selected titles and comments
        translate_prompt_path = prompts_dir / "translate.md"
        if translate_prompt_path.exists():
            translate_prompt = translate_prompt_path.read_text(encoding="utf-8")
            self.logger.info("Translating selected content")
            content = self.llm_provider.translate_selection(content, selection, translate_prompt)
            # Persist translated content so downstream steps (render, re-runs) see it
            if self.content_preparer is not None:
                self.content_preparer.save_content(content, content.date)
        else:
            self.logger.info("No translate.md found, skipping translation step")

        comments_json = self.llm_provider.build_comments_json(content, selection)

        self.logger.info("Round 2: Script generation")
        script = self.llm_provider.generate_script(
            selection=selection,
            comments_json=comments_json,
            script_prompt_template=script_prompt_text,
            date=content.date,
            product=product
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

    def generate_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None, product: str = "full") -> str:
        if product == "daily_brief":
            return self._generate_brief_transcript(script, date, content)
        elif product == "deep_dive":
            return self._generate_deep_dive_transcript(script, date, content)
        else:
            return self._generate_full_transcript(script, date, content)

    def _generate_full_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> str:
        lines = [f"# {script.title} - {date}", ""]
        if script.description:
            lines.append(f"> {script.description}")
            lines.append("")
        if script.tags:
            lines.append(f"标签：{'、'.join(script.tags)}")
            lines.append("")

        # Dashboard section
        dashboard = getattr(script, 'dashboard', None) or (script.segments[0].meta.get('dashboard') if script.segments else None)
        if dashboard:
            lines.append("---")
            lines.append("")
            lines.append("## 今日看点")
            lines.append("")
            entries = dashboard.get("entries", [])
            for entry in entries:
                rank = entry.get("rank", "")
                title = entry.get("original_title", "")
                title_cn = entry.get("title_translation", "")
                score = entry.get("score", "")
                comments = entry.get("comment_count", "")
                score_str = f" ▲ {score}" if score else ""
                comments_str = f" · {comments} comments" if comments else ""
                if title_cn:
                    lines.append(f"{rank}. **{title}** / {title_cn}{score_str}{comments_str}")
                else:
                    lines.append(f"{rank}. **{title}**{score_str}{comments_str}")
            lines.append("")
        elif content:
            dashboard_items = self._collect_dashboard_items(script, content)
            if dashboard_items:
                lines.append("---")
                lines.append("")
                lines.append("## 今日看点")
                lines.append("")
                for i, item in enumerate(dashboard_items, 1):
                    score_str = f" ▲ {item['score']}" if item.get("score") else ""
                    comments_str = f" · {item['comment_count']} comments" if item.get("comment_count") else ""
                    title_cn = item.get("title_cn")
                    if title_cn:
                        lines.append(f"{i}. **{item['title']}** / {title_cn}{score_str}{comments_str}")
                    else:
                        lines.append(f"{i}. **{item['title']}**{score_str}{comments_str}")
                lines.append("")

        # Segments
        item_num = 0
        deep_dive_segment = None
        closing_segment = None
        content_segments = []

        for segment in script.segments:
            if segment.segment_type == "opening":
                # Opening: just date + brief stats, not full audio_text
                lines.append("---")
                lines.append("")
                lines.append("## 开场")
                lines.append("")
                # Extract stats from title_card scene_element
                for elem in segment.scene_elements:
                    if elem.element_type == "title_card":
                        stats = elem.props.get("stats", "")
                        if stats:
                            lines.append(stats)
                        break
                lines.append("")
            elif segment.segment_type == "closing":
                closing_segment = segment
            else:
                content_segments.append(segment)
                if segment.segment_type == "deep_dive":
                    deep_dive_segment = segment

        for segment in content_segments:
            item_num += 1
            label = SEGMENT_TYPE_LABELS.get(segment.segment_type, segment.segment_type)
            lines.append("---")
            lines.append("")
            lines.append(f"## {item_num}. {label}")

            story_title = segment.meta.get("story_title") if segment.meta else None
            if story_title:
                # Try to get title_cn from content package
                title_cn = None
                if content:
                    for elem in segment.scene_elements:
                        story_idx = elem.props.get("story_index")
                        if story_idx is not None and story_idx < len(content.items):
                            title_cn = content.items[story_idx].title_cn
                            break
                if title_cn:
                    lines.append(f"### {title_cn}")
                    lines.append(f"*{story_title}*")
                else:
                    lines.append(f"### {story_title}")

            lines.append("")
            lines.append(segment.audio_text)
            lines.append("")

            # Deep dive: viewpoints + featured quotes
            if segment.segment_type == "deep_dive":
                self._append_deep_dive_rich(lines, segment, content)

            # Medium dive: featured comment
            elif segment.segment_type == "medium_dive":
                self._append_medium_rich(lines, segment, content)

            # Quick news: item summaries
            elif segment.segment_type == "quick_news":
                self._append_quick_rich(lines, segment, content)

        # Summary section (from closing)
        if closing_segment:
            lines.append("---")
            lines.append("")
            lines.append("## 总结")
            lines.append("")
            lines.append(closing_segment.audio_text)
            lines.append("")

            # Closing question from scene_elements
            for elem in closing_segment.scene_elements:
                if elem.element_type == "closing_card":
                    question = elem.props.get("question")
                    if question:
                        lines.append(f"**思考：**{question}")
                        lines.append("")

        return "\n".join(lines)

    def _collect_dashboard_items(self, script: Script, content: Optional[ContentPackage] = None) -> list:
        """Collect story titles and metadata for the dashboard section."""
        items = []
        seen_indices = set()

        for segment in script.segments:
            for elem in segment.scene_elements:
                story_idx = elem.props.get("story_index")
                if story_idx is not None and story_idx not in seen_indices:
                    seen_indices.add(story_idx)
                    entry = {"title": "", "title_cn": None, "score": None, "comment_count": None}

                    # Try to get from content package
                    if content and story_idx < len(content.items):
                        item = content.items[story_idx]
                        entry["title"] = item.title
                        entry["title_cn"] = item.title_cn
                        entry["score"] = item.score
                        entry["comment_count"] = item.comment_count

                    # Fallback: try to get title from segment meta
                    if not entry["title"]:
                        if segment.segment_type == "deep_dive":
                            dd = segment.meta.get("deep_dive", {})
                            entry["title"] = dd.get("story_title", "")
                        elif segment.segment_type == "medium_dive":
                            mi = segment.meta.get("medium_item", {})
                            entry["title"] = mi.get("summary", "") or mi.get("story_title", "")

                    if entry["title"]:
                        items.append(entry)

        return items

    def _append_deep_dive_rich(self, lines: list, segment: ScriptSegment, content: Optional[ContentPackage] = None) -> None:
        dd = segment.meta.get("deep_dive", {}) if segment.meta else {}
        if not dd:
            return

        # Viewpoint camps (new format)
        camps = dd.get("viewpoint_camps", [])
        if camps:
            lines.append("**观点阵营：**")
            lines.append("")
            for camp in camps:
                position = camp.get("position", "")
                key_points = camp.get("key_points", [])
                quote = camp.get("representative_quote", "")
                author = camp.get("quote_author", "")
                lines.append(f"- **{position}**")
                for kp in key_points:
                    lines.append(f"  - {kp}")
                if quote:
                    author_str = f" — {author}" if author else ""
                    lines.append(f"  > \"{quote}\"{author_str}")
            lines.append("")

        # Fallback: perspective_a/b (legacy format)
        if not camps:
            pa = dd.get("perspective_a")
            pb = dd.get("perspective_b")
            if pa or pb:
                lines.append("**观点阵营：**")
                lines.append("")
                if pa:
                    lines.append(f"- **{pa.get('label', '观点 A')}**：{pa.get('core_argument', '')}")
                    rc = pa.get("representative_comment", {})
                    if rc.get("text"):
                        translation = rc.get("translation", "")
                        author = rc.get("author", "")
                        author_str = f" — {author}" if author else ""
                        lines.append(f"  > \"{rc['text']}\"{author_str}")
                        if translation:
                            lines.append(f"  > 解读：{translation}")
                if pb:
                    lines.append(f"- **{pb.get('label', '观点 B')}**：{pb.get('core_argument', '')}")
                    rc = pb.get("representative_comment", {})
                    if rc.get("text"):
                        translation = rc.get("translation", "")
                        author = rc.get("author", "")
                        author_str = f" — {author}" if author else ""
                        lines.append(f"  > \"{rc['text']}\"{author_str}")
                        if translation:
                            lines.append(f"  > 解读：{translation}")
                lines.append("")

        # Selected comments (new format)
        selected_comments = dd.get("selected_comments", [])
        if selected_comments:
            lines.append("**精选评论：**")
            lines.append("")
            for sc in selected_comments[:4]:
                author = sc.get("author", "")
                text = sc.get("text", "")
                sentiment = sc.get("sentiment", "")
                author_str = f"@{author}" if author else ""
                sentiment_str = f" [{sentiment}]" if sentiment else ""
                if text:
                    lines.append(f"- {author_str}{sentiment_str}: {text}")
            lines.append("")

        # Featured comments (legacy format, fallback)
        if not selected_comments:
            featured = dd.get("featured_comments", [])
            if featured:
                lines.append("**精选评论：**")
                lines.append("")
                for fc in featured[:3]:
                    author = fc.get("author", "")
                    text = fc.get("text", "")
                    translation = fc.get("translation", "")
                    angle = fc.get("angle_brief", "")
                    if text:
                        prefix = f"@{author}" if author else ""
                        angle_str = f" ({angle})" if angle else ""
                        if translation:
                            lines.append(f"- {prefix}{angle_str}: {translation}")
                            lines.append(f"  *\"{text}\"*")
                        else:
                            lines.append(f"- {prefix}{angle_str}: {text}")
                lines.append("")

        # Synthesis
        synthesis = dd.get("synthesis", [])
        if synthesis:
            lines.append("**洞察：**")
            lines.append("")
            for s in synthesis:
                lines.append(f"- {s}")
            lines.append("")

        # Host take
        host_take = dd.get("host_take")
        if host_take:
            lines.append(f"**主播态度：**{host_take}")
            lines.append("")

    def _append_medium_rich(self, lines: list, segment: ScriptSegment, content: Optional[ContentPackage] = None) -> None:
        mi = segment.meta.get("medium_item", {}) if segment.meta else {}
        if not mi:
            return

        fc = mi.get("featured_comment", {})
        if fc and fc.get("text"):
            lines.append("**精选评论：**")
            lines.append("")
            author = fc.get("author", "")
            text = fc.get("text", "")
            translation = fc.get("translation", "")
            text_cn = fc.get("text_cn")
            author_str = f"@{author}: " if author else ""
            # Bilingual: show Chinese first if available
            cn_text = translation or text_cn
            if cn_text:
                lines.append(f"> {author_str}{cn_text}")
                lines.append(f"> *\"{text}\"*")
            else:
                lines.append(f"> {author_str}\"{text}\"")
            lines.append("")

        transition = mi.get("transition_note")
        if transition:
            lines.append(f"*{transition}*")
            lines.append("")

    def _append_quick_rich(self, lines: list, segment: ScriptSegment, content: Optional[ContentPackage] = None) -> None:
        qi_list = segment.meta.get("quick_items", []) if segment.meta else []
        if not qi_list:
            return

        lines.append("**快讯列表：**")
        lines.append("")
        for qi in qi_list:
            summary = qi.get("summary", "")
            fc = qi.get("featured_comment", {})
            quote = fc.get("translation") or fc.get("text_cn") or fc.get("text", "") if fc else ""
            original = fc.get("text", "") if fc else ""
            line = f"- {summary}" if summary else ""
            if quote and original and quote != original:
                line += f"\n  > {quote}\n  > *\"{original}\"*" if line else f"> {quote}\n> *\"{original}\"*"
            elif quote:
                line += f"\n  > \"{quote}\"" if line else f"> \"{quote}\""
            if line:
                lines.append(line)
        lines.append("")


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

    def _generate_deep_dive_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None) -> str:
        """Generate long-form article markdown for deep dive product."""
        lines = [f"# {script.title}", ""]
        if script.description:
            lines.append(f"> {script.description}")
            lines.append("")
        if script.tags:
            lines.append(f"标签：{'、'.join(script.tags)}")
            lines.append("")

        # Extract story info for reference
        dd_meta = {}
        for seg in script.segments:
            if seg.segment_type == "deep_dive" and seg.meta:
                dd_meta = seg.meta.get("deep_dive", {})
                break

        story_title = ""
        story_index = dd_meta.get("story_index", 0)
        if content and story_index < len(content.items):
            item = content.items[story_index]
            story_title = item.title
            lines.append("---")
            lines.append("")
            lines.append("## 原始讨论")
            lines.append("")
            title_cn = item.title_cn
            if title_cn:
                lines.append(f"**{title_cn}**")
                lines.append(f"*{story_title}*")
            else:
                lines.append(f"**{story_title}**")
            if item.score:
                lines.append(f"▲ {item.score} · {item.comment_count or 0} comments")
            lines.append("")

        # Segments in order
        segment_num = 0
        for segment in script.segments:
            if segment.segment_type == "opening":
                lines.append("---")
                lines.append("")
                lines.append("## 开场")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")

            elif segment.segment_type == "context":
                lines.append("---")
                lines.append("")
                lines.append("## 背景")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")

            elif segment.segment_type in ("viewpoint_a", "viewpoint_b"):
                segment_num += 1
                camp_label = "阵营一" if segment.segment_type == "viewpoint_a" else "阵营二"
                lines.append("---")
                lines.append("")
                lines.append(f"## {camp_label}")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")
                # Add comment cards
                for elem in segment.scene_elements:
                    if elem.element_type in ("comment_card", "comment_bubble"):
                        self._append_comment_to_lines(lines, elem, content)

            elif segment.segment_type == "comment_deep":
                lines.append("---")
                lines.append("")
                lines.append("## 另类视角")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")
                # List each selected comment with its "why notable"
                for elem in segment.scene_elements:
                    if elem.element_type == "comment_card":
                        self._append_comment_to_lines(lines, elem, content)

            elif segment.segment_type == "synthesis":
                lines.append("---")
                lines.append("")
                lines.append("## 洞察")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")

            elif segment.segment_type == "closing":
                lines.append("---")
                lines.append("")
                lines.append("## 我的立场")
                lines.append("")
                lines.append(segment.audio_text)
                lines.append("")
                # Closing question
                for elem in segment.scene_elements:
                    if elem.element_type == "closing_card":
                        question = elem.props.get("question")
                        if question:
                            lines.append(f"**思考：**{question}")
                            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _append_comment_to_lines(lines: list, elem, content) -> None:
        """Append a single comment to transcript lines."""
        props = elem.props
        author = props.get("author", "")
        text = props.get("text", "") or props.get("original_text", "")
        translation = props.get("translation", "") or props.get("chinese_summary", "")
        why_notable = props.get("why_notable", "")
        if author or text:
            if translation:
                lines.append(f"> @{author}: {translation}")
                lines.append(f"> *\"{text}\"*")
            elif text:
                lines.append(f"> @{author}: \"{text}\"")
            if why_notable:
                lines.append(f"> 为什么值得看：{why_notable}")
            lines.append("")

    def save_transcript(self, script: Script, date: str, content: Optional[ContentPackage] = None, product: str = "full") -> Path:
        path = Path(f"data/{date}/transcript.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        md_content = self.generate_transcript(script, date, content, product)
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

        from src.core.models import ScriptSegment, SceneElement, Cue

        try:
            segments = []
            for seg_dict in script_dict["segments"]:
                scene_elements = [
                    SceneElement(
                        element_type=e["element_type"],
                        start_time=e["start_time"],
                        end_time=e["end_time"],
                        props=e["props"]
                    )
                    for e in seg_dict.get("scene_elements", [])
                ]
                cues = [
                    Cue(
                        text=c["text"],
                        start_time=c["start_time"],
                        end_time=c["end_time"],
                    )
                    for c in seg_dict.get("cues", [])
                ]
                segments.append(ScriptSegment(
                    segment_type=seg_dict["segment_type"],
                    audio_text=seg_dict["audio_text"],
                    estimated_duration=seg_dict["estimated_duration"],
                    actual_duration=seg_dict.get("actual_duration"),
                    emotion=seg_dict.get("emotion", "neutral"),
                    scene_elements=scene_elements,
                    meta=seg_dict.get("meta", {}),
                    start_time=seg_dict.get("start_time"),
                    end_time=seg_dict.get("end_time"),
                    audio_path=seg_dict.get("audio_path"),
                    cues=cues,
                ))

            return Script(
                title=script_dict["title"],
                description=script_dict["description"],
                tags=script_dict["tags"],
                segments=segments,
                total_duration=script_dict.get("total_duration")
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"Script file {path} has unexpected structure: {e}") from e

    def write_from_selection(
        self,
        content: ContentPackage,
        selection_raw: str,
        script_prompt_template: str,
        product: str = "full"
    ) -> Script:
        if selection_raw.endswith(".json"):
            with open(selection_raw, "r", encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = selection_raw

        sd = json.loads(raw) if isinstance(raw, str) else raw
        selection = SelectionResult(
            deep_dive_decision=sd.get("deep_dive_decision", {}),
            quick_selections=sd.get("quick_selections", []),
            medium_selections=sd.get("medium_selections", []),
            patterns=sd.get("patterns", []),
            raw_json=json.dumps(sd, ensure_ascii=False, indent=2)
        )

        comments_json = self.llm_provider.build_comments_json(content, selection)

        script_prompt_template = self._inject_persona(script_prompt_template, Path("prompts"))

        self.logger.info("Debug mode: Skipping R1, using provided selection")
        script = self.llm_provider.generate_script(
            selection=selection,
            comments_json=comments_json,
            script_prompt_template=script_prompt_template,
            date=content.date,
            product=product
        )
        return script
