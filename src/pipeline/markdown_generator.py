from pathlib import Path

from src.core.models import ContentPackage, Script
from src.utils.logger import setup_logger


class MarkdownGenerator:
    def __init__(self, debug: bool = False, level=None):
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def generate(self, content: ContentPackage, script: Script, date: str) -> None:
        lines: list[str] = []

        # ── 标题 ──
        lines.append(f"# HN TechPulse | {date}")
        lines.append("")

        # ── 故事列表 ──
        lines.append("## 故事列表")
        lines.append("")
        lines.append("| # | 标题 | 分数 | 评论 | 分类 |")
        lines.append("|---|------|------|------|------|")
        for i, item in enumerate(content.items, 1):
            title = item.title_cn or item.title or ""
            score = item.score if item.score is not None else "-"
            comments = item.comment_count if item.comment_count is not None else "-"
            category = item.category or "-"
            lines.append(f"| {i} | {title} | {score} | {comments} | {category} |")
        lines.append("")

        # ── 故事详情 ──
        lines.append("## 故事详情")
        lines.append("")
        for i, item in enumerate(content.items, 1):
            title = item.title_cn or item.title or ""
            lines.append(f"### {i}. {title}")
            lines.append("")
            if item.url:
                lines.append(f"- 链接: {item.url}")
            if item.editor_angle:
                lines.append(f"- 编辑视角: {item.editor_angle}")
            if item.why_it_matters:
                lines.append(f"- 为什么重要: {item.why_it_matters}")
            if item.key_points:
                lines.append("- 要点:")
                for kp in item.key_points:
                    point_text = kp.get("point", "") or kp.get("text", "")
                    if point_text:
                        lines.append(f"  - {point_text}")
            if item.article_summary:
                lines.append(f"- 摘要: {item.article_summary}")
            if item.keywords:
                lines.append(f"- 关键词: {', '.join(item.keywords)}")

            # 精选评论
            if item.comments:
                top_comments = sorted(
                    item.comments,
                    key=lambda c: (c.quality_score or 0, c.upvotes or 0),
                    reverse=True,
                )[:3]
                if top_comments:
                    lines.append("- 精选评论:")
                    for c in top_comments:
                        author = c.author or "anonymous"
                        body = (c.content_cn or c.content or "")[:120]
                        lines.append(f"  - **{author}**: {body}")
            lines.append("")

        # ── 脚本概览 ──
        if script and script.segments:
            lines.append("## 脚本概览")
            lines.append("")
            for seg in script.segments:
                seg_type = seg.segment_type
                text = seg.audio_text.strip()
                duration = seg.actual_duration or seg.estimated_duration
                lines.append(f"### [{seg_type}] ({duration:.1f}s)")
                lines.append("")
                lines.append(text)
                lines.append("")

        output_path = Path(f"data/{date}/output.md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        self.logger.info(f"Markdown 已保存至 {output_path}")
