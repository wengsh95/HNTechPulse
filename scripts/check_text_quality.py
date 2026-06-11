#!/usr/bin/env python3
"""Check regenerated text artifacts for common publish-copy failures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BLOCKED_UNRELATED_TERMS = (
    "ChatDev",
    "六成Token",
    "六成 Token",
    "代码审查",
    "审查先吃",
    "Agent写代码",
)

ENGAGEMENT_CLICHES = (
    "三连",
    "点赞",
    "投币",
    "收藏",
    "欢迎订阅",
    "欢迎关注",
)

OVERCLAIM_TERMS = (
    "断网",
    "掉线",
    "违法",
    "法律已生效",
    "彻底",
    "确认结果",
    "没有技术障碍",
    "无技术障碍",
    "几乎没有新增成本",
)

TITLE_OVERCLAIM_TERMS = (
    "断网",
    "掉线",
    "砍掉P2P",
    "砍掉 P2P",
    "一刀砍",
)

BAD_ACCOUNT_INCIDENT_VERBS = (
    "交出两万账号",
    "交出超2万账号",
    "交出账号",
    "放走两万账号",
    "放走超2万账号",
    "放走账号",
    "送走两万账号",
    "送走超2万账号",
    "送走账号",
)

LEGAL_ASSERTION_PATTERNS = (
    "法案过了",
    "已对.*提起诉讼",
)


GENERIC_STORY_TERMS = {
    "AI",
    "API",
    "Linux",
    "GitHub",
    "Windows",
    "macOS",
    "开源",
    "开发者",
    "用户",
    "玩家",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _flatten_title_payload(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "description", "cover_title", "cover_subtitle"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    for key in ("title_candidates", "cover_tags", "tags"):
        values = payload.get(key) or []
        if isinstance(values, list):
            parts.extend(str(v) for v in values if v)
    return "\n".join(parts)


def _public_cover_payload(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "cover_title", "cover_subtitle"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    cover_tags = payload.get("cover_tags") or []
    if isinstance(cover_tags, list):
        parts.extend(str(v) for v in cover_tags if v)
    return "\n".join(parts)


def _story_terms(item: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    fields = (
        item.get("title"),
        item.get("title_cn"),
        item.get("editor_angle"),
    )
    for value in fields:
        if not value:
            continue
        for token in re.findall(
            r"[A-Za-z][A-Za-z0-9.+#-]{2,}|[\u4e00-\u9fff]{2,}", str(value)
        ):
            if token not in GENERIC_STORY_TERMS:
                terms.add(token)
    for keyword in item.get("keywords") or []:
        keyword = str(keyword).strip()
        if keyword and keyword not in GENERIC_STORY_TERMS:
            terms.add(keyword)
    return terms


def _matched_story_indexes(text: str, items: list[dict[str, Any]]) -> list[int]:
    matched: list[int] = []
    for idx, item in enumerate(items):
        terms = _story_terms(item)
        if any(term and term in text for term in terms):
            matched.append(idx)
    return matched


def _guide_public_sections(text: str) -> str:
    if not text:
        return ""
    stop_markers = (
        "\n## 3. 完整发布 Checklist",
        "\n## 4. 注意事项",
        "\n## 3. 注意事项",
    )
    end = len(text)
    for marker in stop_markers:
        idx = text.find(marker)
        if idx >= 0:
            end = min(end, idx)
    return text[:end]


def _guide_publish_copy(text: str) -> str:
    if not text:
        return ""
    start_marker = "\n## 二、B 站发布优化"
    start = text.find(start_marker)
    if start < 0:
        start_marker = "\n## 2. B 站发布优化"
        start = text.find(start_marker)
    if start >= 0:
        text = text[start:]
    stop_markers = (
        "\n## 三、完整发布 Checklist",
        "\n## 3. 完整发布 Checklist",
        "\n## 四、注意事项",
        "\n## 4. 注意事项",
        "\n## 3. 注意事项",
    )
    end = len(text)
    for marker in stop_markers:
        idx = text.find(marker)
        if idx >= 0:
            end = min(end, idx)
    text = text[:end]
    lines: list[str] = []
    skip = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### 运营复盘点"):
            skip = True
            continue
        if stripped.startswith("---") or stripped.startswith("### "):
            skip = False
        if not skip:
            lines.append(line)
    return "\n".join(lines)


def _transcript_public_text(text: str) -> str:
    if not text:
        return ""
    lines = []
    skip_prefixes = ("▲ ", "🖼", "**社区观点**", "**争议焦点**")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        if stripped.startswith(skip_prefixes):
            continue
        if stripped.startswith(">"):
            lines.append(stripped.lstrip("> "))
        elif not stripped.startswith("["):
            lines.append(stripped)
    return "\n".join(lines)


def _add_contains_issues(
    issues: list[dict[str, str]],
    *,
    text: str,
    terms: tuple[str, ...],
    code: str,
    path: str,
) -> None:
    for term in terms:
        if term in text:
            issues.append({"code": code, "path": path, "detail": term})


def check_date(date: str) -> dict[str, Any]:
    base = ROOT / "data" / date
    title_path = base / "title.json"
    transcript_path = base / "transcript.md"
    guide_path = base / "publish_guide.md"
    title = _read_json(title_path)
    title_text = _flatten_title_payload(title)
    cover_text = _public_cover_payload(title)
    content = _read_json(base / "content.json")
    items = content.get("items") if isinstance(content.get("items"), list) else []
    transcript = _read_text(transcript_path)
    guide = _read_text(guide_path)
    publish_copy = _guide_publish_copy(guide)
    public_transcript = _transcript_public_text(transcript)
    combined = "\n".join([title_text, public_transcript, publish_copy])

    issues: list[dict[str, str]] = []
    if not title_path.exists():
        issues.append({"code": "missing_title", "path": str(title_path), "detail": ""})
    if not transcript_path.exists():
        issues.append(
            {"code": "missing_transcript", "path": str(transcript_path), "detail": ""}
        )
    if not guide_path.exists():
        issues.append(
            {"code": "missing_publish_guide", "path": str(guide_path), "detail": ""}
        )

    _add_contains_issues(
        issues,
        text=combined,
        terms=BLOCKED_UNRELATED_TERMS,
        code="unrelated_or_stale_topic",
        path="text_artifacts",
    )
    _add_contains_issues(
        issues,
        text=title_text,
        terms=TITLE_OVERCLAIM_TERMS,
        code="title_overclaim",
        path=str(title_path),
    )
    _add_contains_issues(
        issues,
        text=title_text,
        terms=BAD_ACCOUNT_INCIDENT_VERBS,
        code="bad_account_incident_verb",
        path=str(title_path),
    )
    _add_contains_issues(
        issues,
        text=combined,
        terms=OVERCLAIM_TERMS,
        code="overclaim",
        path="text_artifacts",
    )
    _add_contains_issues(
        issues,
        text=publish_copy,
        terms=ENGAGEMENT_CLICHES,
        code="engagement_cliche",
        path=str(guide_path),
    )

    if re.search(r"Linux.{0,8}(占|近|约)?三成", combined):
        issues.append(
            {
                "code": "linux_percentage_overgeneralized",
                "path": "text_artifacts",
                "detail": "Linux/三成",
            }
        )
    if re.search(r"Linux.{0,8}27\.?7%", combined):
        issues.append(
            {
                "code": "linux_percentage_overgeneralized",
                "path": "text_artifacts",
                "detail": "Linux/27.7%",
            }
        )
    for pattern in LEGAL_ASSERTION_PATTERNS:
        if re.search(pattern, combined):
            issues.append(
                {
                    "code": "legal_assertion_needs_attribution",
                    "path": "text_artifacts",
                    "detail": pattern,
                }
            )

    if len(items) >= 2 and cover_text:
        matched = _matched_story_indexes(cover_text, items)
        if len(matched) > 1:
            issues.append(
                {
                    "code": "title_cover_multiple_stories",
                    "path": str(title_path),
                    "detail": ", ".join(str(i + 1) for i in matched),
                }
            )

    return {
        "date": date,
        "status": "ok" if not issues else "issues",
        "issue_count": len(issues),
        "issues": issues,
        "title": title.get("title", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+")
    args = parser.parse_args()
    results = [check_date(date) for date in args.dates]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(r["issues"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
