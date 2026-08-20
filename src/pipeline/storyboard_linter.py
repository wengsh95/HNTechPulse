"""Deterministic quality linter for storyboard and subtitle plans."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.pipeline.paths import pipeline_path
from src.pipeline.storyboard import load_storyboard


@dataclass(frozen=True)
class LintIssue:
    level: str  # "error" or "warning"
    category: str
    shot_id: str | None
    message: str


def lint_storyboard_and_script(date: str) -> list[LintIssue]:
    """Run deterministic static assertions on storyboard and script artifacts."""
    issues: list[LintIssue] = []

    sb_payload = load_storyboard(date)
    if not sb_payload:
        issues.append(
            LintIssue(
                level="error",
                category="missing_file",
                shot_id=None,
                message=f"storyboard.json missing for date {date}",
            )
        )
        return issues

    shots = sb_payload.get("shots", [])
    if not shots:
        issues.append(
            LintIssue(
                level="error",
                category="empty_storyboard",
                shot_id=None,
                message="storyboard.json contains no shots",
            )
        )
        return issues

    # 1. Validate each shot
    for shot in shots:
        shot_id = shot.get("shot_id", "UNKNOWN")
        template_id = shot.get("template_id")
        props = shot.get("props") or {}

        if not template_id:
            issues.append(
                LintIssue(
                    level="error",
                    category="missing_template",
                    shot_id=shot_id,
                    message="Shot is missing template_id",
                )
            )
            continue

        # Template specific assertions
        if template_id == "cover_v1":
            if not props.get("headline"):
                issues.append(
                    LintIssue(
                        level="error",
                        category="missing_props",
                        shot_id=shot_id,
                        message="cover_v1 shot missing 'headline'",
                    )
                )

        elif template_id in {"closing_v1", "closing_signals_v1"}:
            has_summary = bool(
                props.get("summary_items")
                or props.get("takeaways")
                or props.get("items")
                or props.get("signal")
            )
            if not has_summary:
                issues.append(
                    LintIssue(
                        level="error",
                        category="empty_closing",
                        shot_id=shot_id,
                        message="Closing card has empty summary/takeaways/items props",
                    )
                )

        elif template_id == "comment_single_v1":
            quote = str(props.get("quote") or "").strip()
            if not quote or quote in {"暂无可用的评论摘录。"}:
                issues.append(
                    LintIssue(
                        level="warning",
                        category="weak_quote",
                        shot_id=shot_id,
                        message="comment_single_v1 shot has placeholder or empty quote",
                    )
                )

        elif template_id == "quick_news_v1":
            if not props.get("title") or not props.get("fact"):
                issues.append(
                    LintIssue(
                        level="error",
                        category="missing_props",
                        shot_id=shot_id,
                        message="quick_news_v1 shot missing 'title' or 'fact'",
                    )
                )

    # 2. Validate script.json and subtitle formatting
    script_path = pipeline_path(date, "script.json")
    if script_path.exists():
        try:
            script_data = json.loads(script_path.read_text(encoding="utf-8"))
            for seg_idx, seg in enumerate(script_data.get("segments", [])):
                for elem_idx, elem in enumerate(seg.get("scene_elements", [])):
                    props = elem.get("props") or {}
                    subtitles = props.get("subtitle_texts") or []
                    for sub in subtitles:
                        sub_str = str(sub).strip()
                        # Check abnormal whitespace between CJK
                        if re.search(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", sub_str):
                            issues.append(
                                LintIssue(
                                    level="warning",
                                    category="cjk_spacing",
                                    shot_id=f"Seg{seg_idx}-Elem{elem_idx}",
                                    message=f"Subtitle contains inner CJK whitespace: {sub_str!r}",
                                )
                            )
                        # Check dangling connectors at end of subtitle clause before punct
                        cleaned_end = sub_str.rstrip("。！？.,!?；;：: ")
                        if (
                            cleaned_end
                            and cleaned_end[-1] in "在的把让被与和以及及为对从向按跟"
                        ):
                            issues.append(
                                LintIssue(
                                    level="warning",
                                    category="dangling_connector",
                                    shot_id=f"Seg{seg_idx}-Elem{elem_idx}",
                                    message=f"Subtitle ends with dangling connector: {sub_str!r}",
                                )
                            )
        except Exception as exc:
            issues.append(
                LintIssue(
                    level="error",
                    category="invalid_script",
                    shot_id=None,
                    message=f"Failed to read/parse script.json: {exc}",
                )
            )

    return issues
