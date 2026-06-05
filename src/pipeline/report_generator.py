import json
from collections import Counter, defaultdict
from pathlib import Path

from src.utils.logger import setup_logger


class ReportGenerator:
    def __init__(self, debug: bool = False, level=None):
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def _coverage_counts(self, content, script) -> dict[str, int]:
        """Count planned story coverage from script visuals, falling back to legacy indices."""
        counts = {"focus": 0}
        seen: set[tuple[str, int]] = set()

        if script:
            for seg in script.segments:
                for elem in seg.scene_elements:
                    props = elem.props or {}

                    tier = props.get("coverage_tier")
                    if not tier:
                        if elem.element_type in {"event_card", "atmosphere_card"}:
                            tier = "focus"
                    if tier not in counts:
                        continue

                    story_index = props.get("story_index", props.get("display_index"))
                    try:
                        idx = int(story_index)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        idx = len(seen)
                    key = (tier, idx)
                    if key not in seen:
                        seen.add(key)
                        counts[tier] += 1

        if any(counts.values()):
            return counts

        if content:
            return {
                "focus": len(content.deep_dive_indices),
            }

        return counts

    def generate(self, date: str, steps: list, elapsed: float, content, script) -> None:
        base = Path(f"data/{date}")
        lines = [f"# HN TechPulse 执行报告 | {date}", ""]

        # ── 基本信息 ──
        lines.append("## 基本信息")
        lines.append("")
        lines.append("| 项目 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 日期 | {date} |")
        lines.append(f"| 执行步骤 | {', '.join(steps)} |")
        lines.append(f"| 总耗时 | {elapsed:.1f}s |")
        if content:
            coverage_counts = self._coverage_counts(content, script)
            lines.append(f"| 故事总数 | {len(content.items)} |")
            lines.append(f"| 深度报道 | {coverage_counts['focus']} |")

            # Video title & description from title.json
            title_data = self._load_json(base / "title.json")
            if title_data:
                lines.append(f"| 视频标题 | {title_data.get('title', '-')} |")
                desc = title_data.get("description", "-")
                lines.append(
                    f"| 视频简介 | {desc[:120]}{'...' if len(desc) > 120 else ''} |"
                )
                tags = title_data.get("tags", [])
                if tags:
                    lines.append(f"| 标签 | {', '.join(tags)} |")
        else:
            lines.append("| 故事总数 | N/A |")

        # ── Prefilter 统计 ──
        prefilter_data = self._load_json(base / "prefilter.json")
        if prefilter_data:
            stats = prefilter_data.get("stats", {})
            if stats:
                lines.append("")
                lines.append("## Prefilter 统计")
                lines.append("")
                lines.append("| 指标 | 值 |")
                lines.append("|------|-----|")
                lines.append(f"| 候选总数 | {stats.get('total', '-')} |")
                lines.append(f"| 保留 | {stats.get('kept', '-')} |")
                lines.append(f"| 过滤 | {stats.get('removed', '-')} |")

        # ── 故事概览 ──
        if content and content.items:
            lines.append("")
            lines.append("## 故事概览")
            lines.append("")
            lines.append(
                "| # | 标题 | 中文标题 | 角度 | 分数 | 评论 | 分类 | 富化 | 图片 |"
            )
            lines.append(
                "|---|------|----------|------|------|------|------|------|------|"
            )
            for i, item in enumerate(content.items, 1):
                title = (item.title or "")[:35]
                title_cn = (item.title_cn or "-")[:30]
                angle = (item.editor_angle or "-")[:25]
                score = item.score if item.score is not None else "-"
                comments = item.comment_count if item.comment_count is not None else "-"
                cat = item.category or "-"
                source = item.enrichment_source or "未富化"
                imgs = len(item.article_images) if item.article_images else 0
                lines.append(
                    f"| {i} | {title} | {title_cn} | {angle} | {score} | {comments} | {cat} | {source} | {imgs} |"
                )

        # ── 富化统计 ──
        source_counts: Counter[str] = Counter()
        total_images = 0
        if content and content.items:
            for item in content.items:
                source_counts[item.enrichment_source or "未富化"] += 1
                total_images += len(item.article_images or [])
            total = len(content.items)
            lines.append("")
            lines.append("## 富化统计")
            lines.append("")
            lines.append("| 策略 | 数量 | 占比 |")
            lines.append("|------|------|------|")
            for strategy in [
                "aiohttp",
                "pdf",
                "headless",
                "headed",
                "downloaded_page",
                "fetch_failed",
                "extraction_failed",
                "skipped",
                "error",
                "manual_override",
                "none",
                "legacy",
                "未富化",
            ]:
                cnt = source_counts.get(strategy, 0)
                if cnt > 0:
                    pct = cnt / total * 100 if total > 0 else 0
                    lines.append(f"| {strategy} | {cnt} | {pct:.0f}% |")
            lines.append(f"- 总图片数: {total_images}")

        # ── 评论分析 ──
        judge_data = self._load_json(base / "comment_judgement.json")
        if judge_data:
            stories_data = judge_data.get("stories", {})
            if stories_data:
                lines.append("")
                lines.append("## 评论分析")
                lines.append("")
                lines.append(
                    "| # | Story | 讨论模式 | Quote 候选 | Counterpoint | Color | Detail |"
                )
                lines.append(
                    "|---|-------|----------|-----------|-------------|-------|--------|"
                )
                for i, item in enumerate(content.items or [], 1):
                    sid = item.source_id
                    sd = stories_data.get(sid, {})
                    mode = sd.get("discussion_mode", "-")
                    lanes = sd.get("comment_lanes", {})
                    n_candidates = sum(len(v) for v in lanes.values())
                    n_counterpoint = len(lanes.get("counterpoint", []))
                    n_color = len(lanes.get("color", []))
                    n_detail = len(lanes.get("detail", []))
                    title_short = (item.title or "")[:30]
                    lines.append(
                        f"| {i} | {title_short} | {mode} | {n_candidates} | {n_counterpoint} | {n_color} | {n_detail} |"
                    )

        # ── 脚本概览 ──
        if script and script.segments:
            seg_stats: defaultdict[str, dict[str, float]] = defaultdict(
                lambda: {"count": 0, "est": 0.0, "act": 0.0}
            )
            for seg in script.segments:
                st = seg.segment_type
                seg_stats[st]["count"] += 1
                seg_stats[st]["est"] += seg.duration
                seg_stats[st]["act"] += seg.actual_duration or seg.duration
            lines.append("")
            lines.append("## 脚本概览")
            lines.append("")
            lines.append("| 片段类型 | 数量 | 时长 |")
            lines.append("|----------|------|------|")
            for st in ["opening", "story_scan", "closing"]:
                if st in seg_stats:
                    s = seg_stats[st]
                    lines.append(f"| {st} | {s['count']} | {s['act']:.1f}s |")
            for st, s in seg_stats.items():
                if st not in ("opening", "story_scan", "closing"):
                    lines.append(f"| {st} | {s['count']} | {s['act']:.1f}s |")
            total_act = sum(
                seg.actual_duration or seg.duration for seg in script.segments
            )
            lines.append(f"- 视频总时长: {total_act:.1f}s")

            # Audio stats
            audio_dir = base / "audio"
            if audio_dir.exists():
                audio_files = list(audio_dir.iterdir())
                if audio_files:
                    total_audio_mb = sum(
                        f.stat().st_size for f in audio_files if f.is_file()
                    ) / (1024 * 1024)
                    lines.append(f"- 音频文件数: {len(audio_files)}")
                    lines.append(f"- 音频总大小: {total_audio_mb:.1f} MB")

        # ── 翻译统计 ──
        translations_data = self._load_json(base / "translations.json")
        if translations_data:
            comment_keys = [k for k in translations_data if k.startswith("comment_")]
            title_keys = [k for k in translations_data if k.startswith("title_")]
            lines.append("")
            lines.append("## 翻译统计")
            lines.append("")
            lines.append("| 类型 | 数量 |")
            lines.append("|------|------|")
            lines.append(f"| 标题翻译 | {len(title_keys)} |")
            lines.append(f"| 评论翻译 | {len(comment_keys)} |")

        # ── 问题列表 ──
        issues = []
        manual_override_items = []
        if content:
            for i, item in enumerate(content.items, 1):
                if item.enrichment_source in (
                    "fetch_failed",
                    "extraction_failed",
                    "error",
                ):
                    title = (item.title or "")[:40]
                    url = (item.url or "")[:60]
                    reason = item.enrichment_source
                    issues.append(f"- [需手动处理] #{i} {title} — {reason}")
                    manual_override_items.append(f"  - #{i} {title}: {url}")
                if (
                    item.enrichment_source in ("aiohttp", "headless", "headed", "pdf")
                    and not item.article_images
                ):
                    title = (item.title or "")[:40]
                    issues.append(f"- [缺少图片] #{i} {title} — 富化成功但无图片")
        if script:
            for idx, seg in enumerate(script.segments):
                if seg.actual_duration and seg.duration and seg.duration > 0:
                    ratio = seg.actual_duration / seg.duration
                    if ratio < 0.6 and seg.segment_type not in ("opening", "closing"):
                        issues.append(
                            f"- [时长偏短] 片段 {idx} [{seg.segment_type}] "
                            f"实际{seg.actual_duration:.1f}s / 预计{seg.duration:.1f}s (比率{ratio:.2f})"
                        )
        lines.append("")
        lines.append("## 问题列表")
        lines.append("")
        if issues:
            lines.extend(issues)
        else:
            lines.append("无")

        # ── 手动处理指引 ──
        if manual_override_items:
            lines.append("")
            lines.append("## 需要手动处理")
            lines.append("")
            lines.append("以下条目所有自动抓取策略均失败，请手动下载网页：")
            lines.append("")
            lines.extend(manual_override_items)
            lines.append("")
            lines.append(
                f"用浏览器打开对应 URL，保存网页为 HTML 文件到 `data/{date}/downloaded_pages/{{source_id}}.html`。"
            )
            lines.append("完成后重新运行 pipeline，将从断点继续。")

        report_path = base / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self.logger.info(f"执行报告已保存至 {report_path}")

    @staticmethod
    def _load_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
