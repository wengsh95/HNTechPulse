"""Title metadata and cover-image stages."""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import (
    file_sha256,
    is_artifact_fresh,
    stable_hash,
    write_artifact_manifest,
)
from src.pipeline.paths import publish_path, render_path, render_remotion_dir
from src.pipeline.stages.packaging import COVER_VARIANT_COUNT
from src.pipeline.stages.context import OrchestratorContext
from src.utils.atomic_io import atomic_write_json
from src.utils.text import normalize_cjk_mixed_spacing

_PUBLISH_DISCUSSION_CLICHES = (
    "你怎么看，欢迎在评论区聊聊。",
    "欢迎在评论区聊聊。",
    "欢迎评论区聊聊。",
    "你怎么看？",
    "你怎么看。",
)
TITLE_NORMALIZATION_VERSION = 9


def _clean_publish_description(text: str, max_len: int = 130) -> str:
    """Keep generated publishing copy dense enough for Bilibili metadata."""
    text = normalize_cjk_mixed_spacing(str(text or "")).strip()
    for phrase in _PUBLISH_DISCUSSION_CLICHES:
        text = text.replace(phrase, "")
    text = text.replace("；", "。").replace(";", "。")
    text = re.sub(r"\s+", " ", text).strip()
    # LLM output and the later "ensure every story is mentioned" pass can
    # occasionally repeat the exact same sentence.  Publishing metadata
    # should never preserve that mechanical duplication.
    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = part.strip()
        key = part.rstrip("。！？!?").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    text = "".join(deduped)
    if len(text) <= max_len:
        return text

    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    kept: list[str] = []
    total = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if kept and total + len(part) > max_len:
            break
        kept.append(part)
        total += len(part)
    compacted = "".join(kept).strip()
    if compacted:
        return compacted
    return text[:max_len].rstrip("，。！？；：,.!?;: ")


def _downgrade_unsupported_publish_claims(text: str) -> str:
    """Tone down recurring high-conflict copy that overstates source facts."""
    text = normalize_cjk_mixed_spacing(str(text or ""))
    replacements = {
        # Replace whole recurring headline clauses before replacing their
        # individual words.  Word-by-word substitutions used to turn
        # "能不能被暗中削弱" into the visibly broken
        # "能不能疑似收到低档输出".
        "能不能被暗中削弱": "是否收到低档输出",
        "不能被暗中削弱": "质疑低档输出",
        "能不能被疑似削弱": "是否收到低档输出",
        "不能被疑似削弱": "质疑低档输出",
        "被疑似A/B": "疑似被纳入A/B",
        "降档高价计费引发争议": "降档计费争议",
        "付费用户疑似被纳入测试": "用户疑似入组",
        "先掉链子": "先多等100毫秒",
        "先掉线": "延迟先升高",
        "掉线": "延迟升高",
        "断网": "延迟升高",
        "砍掉P2P": "改了P2P路径",
        "砍掉 P2P": "改了 P2P 路径",
        "一刀砍": "改动",
        "20225个Instagram账号": "超2万个Instagram账号",
        "20225个账号": "超2万个账号",
        "20225 个账号": "超2万个账号",
        "20225个": "超2万个",
        "先遭殃": "延迟升高",
        "偷偷": "疑似",
        "暗中": "疑似",
        "暗降": "疑似降",
        "暗改": "疑似调整",
        "悄悄": "疑似",
        "缩水算力": "低档输出",
        "被偷走推理": "推理档位引争议",
        "被疑似削弱": "疑似收到低档输出",
        "削弱": "低档输出",
        "被实验": "被纳入测试",
        "实验品": "测试对象",
        "信任崩塌": "信任风险",
        "信任危机": "信任风险",
        "知情权失守": "知情权争议",
        "疑似\n付费信任失守": "被指\n计费引发质疑",
        "信任失守": "信任风险",
        "伤了付费信任": "引发付费信任风险",
        "中招": "受影响",
        "偷工减料": "档位调整",
        "用作成本实验": "成本影响待验证",
        "砍到": "调到",
        "照收高价": "高价计费引发争议",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Keep one uncertainty marker even when separate substitutions put two
    # copies on adjacent cover lines or combine "被指" with "疑似".
    text = re.sub(r"疑似(\s*)疑似", r"\1疑似", text)
    text = re.sub(r"(被曝|被指)([^：\n]{0,14})疑似", r"\1\2", text)
    return text


def _publish_title_width(text: str) -> int:
    """Measure title width with the same compact rule promised in the prompt."""

    body = str(text or "").removeprefix("【HN日报】")
    return sum(1 if ord(char) < 128 else 2 for char in body)


def _validate_cover_title_shape(title: str, *, label: str) -> None:
    """Keep generated cover copy inside the two-line Remotion safe area."""

    lines = str(title or "").splitlines() or [""]
    if len(lines) > 2:
        raise ValueError(f"{label} must use at most two lines")
    widths = [_publish_title_width(line) for line in lines]
    too_wide = [
        f"line {index} width={width}: {line}"
        for index, (line, width) in enumerate(zip(lines, widths), start=1)
        if width > 16
    ]
    if too_wide:
        raise ValueError(
            f"{label} line visual width must be <= 16. " + "; ".join(too_wide)
        )
    if sum(widths) > 32:
        raise ValueError(f"{label} total visual width must be <= 32")


def _normalize_cover_variants(raw: Any) -> list[dict[str, Any]]:
    """Normalize cover copy emitted by the title/editorial LLM call."""
    if not isinstance(raw, list):
        return []

    variants: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # Raw LLM output uses cover_* names.  title.json stores the canonical
        # names below and is read again by the cover stage, so both schemas
        # must round-trip without losing every field.
        title = _downgrade_unsupported_publish_claims(
            str(entry.get("cover_title") or entry.get("title") or "")
        ).strip()
        if not title:
            continue
        subtitle = normalize_cjk_mixed_spacing(
            _downgrade_unsupported_publish_claims(
                str(entry.get("cover_subtitle") or entry.get("subtitle") or "")
            )
        ).strip()
        tags = [
            normalize_cjk_mixed_spacing(
                _downgrade_unsupported_publish_claims(str(tag))
            ).strip()
            for tag in (entry.get("cover_tags") or entry.get("tags") or [])
            if str(tag).strip()
        ][:2]
        highlights = [
            normalize_cjk_mixed_spacing(
                _downgrade_unsupported_publish_claims(str(word))
            ).strip()
            for word in (entry.get("cover_highlights") or entry.get("highlights") or [])
            if str(word).strip()
        ][:4]
        variants.append(
            {
                "title": title,
                "subtitle": subtitle,
                "tags": tags,
                "highlights": highlights,
            }
        )
    return variants[:COVER_VARIANT_COUNT]


def _validate_title_payload(payload: dict) -> None:
    """Reject incomplete or duplicate publish packages while LLM retry is available."""

    if len(str(payload.get("title") or "").strip()) < 8:
        raise ValueError("Publish title must contain at least 8 characters")
    if not str(payload.get("description") or "").strip():
        raise ValueError("Publish description is required")
    variants = _normalize_cover_variants(payload.get("cover_variants"))
    signatures = {stable_hash(variant) for variant in variants}
    if len(variants) != COVER_VARIANT_COUNT or len(signatures) != COVER_VARIANT_COUNT:
        raise ValueError("Exactly three distinct cover_variants are required")
    _validate_cover_title_shape(
        _downgrade_unsupported_publish_claims(payload.get("cover_title") or ""),
        label="cover_title",
    )
    for index, variant in enumerate(variants, start=1):
        _validate_cover_title_shape(
            variant["title"], label=f"cover_variant[{index}].cover_title"
        )
    candidates = [
        str(candidate).strip()
        for candidate in payload.get("title_candidates") or []
        if isinstance(candidate, str) and candidate.strip()
    ]
    if (
        len(candidates) != 3
        or len(set(candidates)) != 3
        or str(payload.get("title") or "").strip() not in candidates
    ):
        raise ValueError(
            "Exactly three distinct title_candidates including title are required"
        )
    too_wide = [
        (candidate, _publish_title_width(candidate))
        for candidate in candidates
        if _publish_title_width(candidate) > 48
    ]
    if too_wide:
        details = "; ".join(
            f"width={width}: {candidate}" for candidate, width in too_wide
        )
        raise ValueError(
            "Publish title visual width must be <= 48. "
            f"Shorten only these offending titles: {details}"
        )

    # When the main cover names a recognizable company or product, every
    # angle must retain one of those tokens.  Otherwise support/risk variants
    # can degrade into generic copy that is meaningless as a thumbnail.
    main_cover = str(payload.get("cover_title") or "")
    subject_tokens = {
        token.lower()
        for token in re.findall(r"[A-Z][A-Za-z0-9.+-]{2,}", main_cover)
        if token.lower() not in {"the", "and", "for", "with"}
    }
    if subject_tokens:
        for variant in variants:
            variant_title = variant["title"].lower()
            if not any(token in variant_title for token in subject_tokens):
                raise ValueError(
                    "Every cover variant must retain the main company or product"
                )


def _validate_title_grounding(payload: dict, focus_story: dict) -> None:
    """Preserve uncertainty from a source across every outward headline."""

    if not _source_requires_uncertainty(focus_story):
        return

    uncertainty_markers = (
        "疑似",
        "被曝",
        "被指",
        "可能",
        "争议",
        "待确认",
        "待验证",
    )
    outward_titles: list[tuple[str, str]] = [
        ("title", str(payload.get("title") or "").strip()),
        ("cover_title", str(payload.get("cover_title") or "").strip()),
    ]
    outward_titles.extend(
        ("title_candidate", str(candidate).strip())
        for candidate in payload.get("title_candidates") or []
        if isinstance(candidate, str)
    )
    outward_titles.extend(
        (
            "cover_variant",
            str(variant.get("cover_title") or variant.get("title") or "").strip(),
        )
        for variant in payload.get("cover_variants") or []
        if isinstance(variant, dict)
    )
    for kind, text in outward_titles:
        if text and not any(marker in text for marker in uncertainty_markers):
            raise ValueError(
                f"Source is uncertain; this {kind} is missing one marker "
                f"(疑似/被曝/被指/可能/争议/待确认/待验证): {text}"
            )


def _source_requires_uncertainty(focus_story: dict) -> bool:
    source_text = " ".join(
        str(focus_story.get(key) or "")
        for key in ("title", "title_cn", "article_summary", "editor_angle")
    ).lower()
    return any(
        marker in source_text
        for marker in (
            " appears ",
            " reportedly ",
            " allegedly ",
            " suspected ",
            "疑似",
            "可能",
            "被指",
            "a/b测试",
        )
    )


def _preserve_source_uncertainty(text: str, focus_story: dict) -> str:
    """Mechanically qualify secondary title candidates when the source is tentative."""

    if not _source_requires_uncertainty(focus_story) or any(
        marker in text for marker in ("疑似", "被曝", "被指", "可能")
    ):
        return text
    prefix = "【HN日报】"
    if text.startswith(prefix):
        return f"{prefix}被曝{text[len(prefix) :]}"
    return f"疑似{text}"


def _normalize_cover_prompt(raw: Any) -> str:
    """Keep a cached image prompt bounded and safe for the image provider."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text[:1200].rstrip(" ,.;。；")
    safety_suffix = (
        "No logos, no text, no watermarks, no brand references, no horizontal bars, "
        "no vertical bars, no UI elements, no header bars, no footer bars."
    )
    if safety_suffix.rstrip(".").lower() not in text.rstrip(".").lower():
        text = f"{text}, {safety_suffix}"
    return text


def _ensure_all_stories_in_description(
    description: str,
    focus_story: dict,
    other_stories: list[dict],
) -> str:
    """Append any story not already mentioned in the description."""

    def _story_keywords(story: dict) -> set[str]:
        src = normalize_cjk_mixed_spacing(
            (story.get("title_cn") or "") + " " + (story.get("editor_angle") or "")
        )
        tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", src))
        generic = {"苹果", "macbook", "ipad", "mac", "iphone"}
        return {token for token in tokens if token not in generic}

    def _story_mentioned(desc: str, story: dict) -> bool:
        source = " ".join(
            str(story.get(key) or "") for key in ("title", "title_cn", "editor_angle")
        )
        ascii_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}", source)
            if token.lower() not in {"the", "and", "for", "with", "from"}
        }
        desc_lower = normalize_cjk_mixed_spacing(desc).lower()
        if ascii_tokens and any(token in desc_lower for token in ascii_tokens):
            return True
        keywords = _story_keywords(story)
        if not keywords:
            return True
        return any(keyword.lower() in desc_lower for keyword in keywords)

    def _compact_line(story: dict) -> str:
        editor = story.get("editor_angle") or ""
        summary = (story.get("article_summary") or "")[:120]
        return normalize_cjk_mixed_spacing(editor or summary)

    extra_lines = []
    for story in other_stories:
        if not _story_mentioned(description, story):
            line = _compact_line(story)
            if line:
                extra_lines.append(line)

    if not extra_lines:
        return description
    return description.rstrip("。；; ") + "。" + "。".join(extra_lines) + "。"


class TitleCoverStageMixin(OrchestratorContext):
    """Generate title metadata and cover backgrounds/props."""

    def _step_title(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Title — generate video title/description/tags")
        if script is None:
            self.logger.warning("Script not loaded; skipping title generation")
            return script

        cache_path = publish_path(date, "title.json")
        focus_story, comment_analysis = self._build_focus_story_input(
            script, content, date
        )
        manifest_inputs = {
            "focus_source_id": focus_story.get("source_id", ""),
            "focus_title": focus_story.get("title", ""),
            "focus_title_cn": focus_story.get("title_cn", ""),
            "focus_editor_angle": focus_story.get("editor_angle", ""),
            "comment_analysis_hash": stable_hash(comment_analysis),
            "prompt_hash": file_sha256(Path("prompts/title.md")),
            "normalization_version": TITLE_NORMALIZATION_VERSION,
            "date": date,
        }

        if is_artifact_fresh(cache_path, manifest_inputs):
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.logger.info(f"  Loaded cached title from {cache_path}")
            script.title = normalize_cjk_mixed_spacing(
                cached.get("title", script.title)
            )
            script.description = cached.get("description", script.description)
            script.tags = cached.get("tags", script.tags)
            script.cover_subtitle = normalize_cjk_mixed_spacing(
                cached.get("cover_subtitle", script.cover_subtitle)
            )
            script.cover_title = normalize_cjk_mixed_spacing(
                cached.get("cover_title", script.cover_title)
            )
            script.cover_tags = [
                normalize_cjk_mixed_spacing(str(tag))
                for tag in (cached.get("cover_tags") or script.cover_tags or [])
                if str(tag).strip()
            ][:2]
            script.cover_highlights = [
                normalize_cjk_mixed_spacing(str(word))
                for word in (
                    cached.get("cover_highlights") or script.cover_highlights or []
                )
                if str(word).strip()
            ][:4]
            return script

        if self.dry_run:
            self.logger.info("Dry run: skipping title generation")
            return script

        other_stories = []
        focus_id = focus_story.get("source_id", "")
        for item in content.items:
            if str(item.source_id) == str(focus_id):
                continue
            other_stories.append(
                {
                    "title": item.title,
                    "title_cn": item.title_cn or "",
                    "editor_angle": item.editor_angle or "",
                    "article_summary": (item.article_summary or "")[:300],
                    "key_points": (item.key_points or [])[:3],
                }
            )

        context = {
            "focus_story_json": json.dumps(focus_story, ensure_ascii=False, indent=2),
            "other_stories_json": json.dumps(
                other_stories, ensure_ascii=False, indent=2
            ),
            "comments_json": json.dumps(comment_analysis, ensure_ascii=False, indent=2),
            "date": date,
        }

        def _title_validator(payload: dict) -> None:
            _validate_title_payload(payload)
            _validate_title_grounding(payload, focus_story)

        try:
            result = self.llm_provider.complete_prompt(
                "prompts/title.md",
                context,
                label="title",
                expect_json=True,
                max_tokens=16384,
                model=self.llm_provider.fast_model,
                temperature=self.llm_provider.fast_temperature,
                validator=_title_validator,
            )
        except (ValueError, Exception) as e:
            self.logger.error(f"  Title LLM call failed: {e}")
            raise
        _title_validator(result)

        chosen = _downgrade_unsupported_publish_claims(result.get("title") or "")
        if chosen and len(chosen) < 8:
            self.logger.warning(
                f"  LLM's `title` field was only {len(chosen)} chars; "
                f"below minimum 8: {chosen!r}"
            )

        script.title = _preserve_source_uncertainty(chosen or "HN每日观察", focus_story)
        desc = (
            _clean_publish_description(
                _downgrade_unsupported_publish_claims(result.get("description") or ""),
                max_len=240,
            )
            or f"每日快讯 - {date}"
        )
        script.description = _clean_publish_description(
            _ensure_all_stories_in_description(desc, focus_story, other_stories),
            max_len=240,
        )
        script.tags = list(result.get("tags") or [])
        script.cover_subtitle = normalize_cjk_mixed_spacing(
            _downgrade_unsupported_publish_claims(result.get("cover_subtitle") or "")
        )
        script.cover_title = _preserve_source_uncertainty(
            _downgrade_unsupported_publish_claims(result.get("cover_title") or ""),
            focus_story,
        )
        script.cover_tags = [
            normalize_cjk_mixed_spacing(_downgrade_unsupported_publish_claims(str(tag)))
            for tag in (result.get("cover_tags") or [])
            if str(tag).strip()
        ][:2]
        script.cover_highlights = [
            normalize_cjk_mixed_spacing(
                _downgrade_unsupported_publish_claims(str(word))
            )
            for word in (result.get("cover_highlights") or [])
            if str(word).strip()
        ][:4]
        cover_variants = _normalize_cover_variants(result.get("cover_variants"))
        cover_prompt = _normalize_cover_prompt(result.get("cover_prompt"))
        if not cover_variants and script.cover_title:
            cover_variants = [
                {
                    "title": script.cover_title,
                    "subtitle": script.cover_subtitle,
                    "tags": script.cover_tags,
                    "highlights": script.cover_highlights,
                }
            ]

        atomic_write_json(
            cache_path,
            {
                "title": script.title,
                "title_candidates": [
                    _preserve_source_uncertainty(
                        _downgrade_unsupported_publish_claims(candidate), focus_story
                    )
                    for candidate in (result.get("title_candidates") or [script.title])
                    if isinstance(candidate, str) and candidate.strip()
                ][:4],
                "description": script.description,
                "cover_title": script.cover_title,
                "cover_tags": script.cover_tags,
                "cover_highlights": script.cover_highlights,
                "cover_subtitle": script.cover_subtitle,
                "cover_variants": cover_variants,
                "cover_prompt": cover_prompt,
                "tags": script.tags,
            },
        )
        write_artifact_manifest(
            cache_path,
            step="title",
            date=date,
            inputs=manifest_inputs,
            config=self.config,
        )
        self.script_writer.save_script(script, date)
        return script

    def _step_cover_image(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Cover image — generate AI image + cached cover text variants"
        )
        bg_path = render_path(date, "cover_bg.png")
        cover_aspect_ratio = "16:9"
        fallback_title = (
            script.cover_title
            if script and script.cover_title
            else script.title
            if script
            else "HN每日观察"
        )
        fallback_tags = script.cover_tags[:2] if script and script.cover_tags else []
        fallback_highlights = (
            script.cover_highlights[:4] if script and script.cover_highlights else []
        )
        if script is None:
            fallback_subtitle = date
        elif script.cover_subtitle:
            fallback_subtitle = script.cover_subtitle
        elif script.description:
            fallback_subtitle = script.description[:40] + (
                "…" if len(script.description) > 40 else ""
            )
        else:
            fallback_subtitle = date
        date_label = date

        cover_prompt = self._load_title_cover_prompt(date)
        if not cover_prompt:
            cover_prompt = (
                "A bold editorial illustration about technology and software, "
                "abstract central metaphor, no logos, no text."
            )
        cover_prompt_hash = stable_hash(cover_prompt)
        cover_cfg = self.config.get("image_generator", {})
        candidate_count = max(
            1,
            int(
                os.environ.get("HN_COVER_CANDIDATES")
                or cover_cfg.get("candidate_count", 1)
                or 1
            ),
        )
        cover_bg_inputs = {
            "prompt_hash": cover_prompt_hash,
            "aspect_ratio": cover_aspect_ratio,
            "candidate_count": candidate_count,
        }
        bg_is_fresh = is_artifact_fresh(bg_path, cover_bg_inputs)

        variants = self._load_title_cover_variants(date)
        fallback_variant = {
            "title": fallback_title,
            "subtitle": fallback_subtitle,
            "tags": fallback_tags,
            "highlights": fallback_highlights,
        }
        if not variants:
            variants = [fallback_variant]
        while len(variants) < COVER_VARIANT_COUNT:
            variants.append(dict(fallback_variant))
        variants = variants[:COVER_VARIANT_COUNT]
        variant_hash = stable_hash(variants)

        variant_paths = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        if bg_is_fresh and all(
            is_artifact_fresh(
                path,
                {
                    "background": bg_path.name,
                    "variant_index": index,
                    "title_cover_variants_hash": variant_hash,
                    "cover_prompt_hash": cover_prompt_hash,
                },
            )
            for index, path in enumerate(variant_paths, start=1)
        ):
            self.logger.info("  Cover image + variants already done; skipping")
            self._mirror_cover_bg(date, bg_path)
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping cover image generation")
            return

        if not bg_is_fresh:
            if self.image_generator is None:
                if not bg_path.exists():
                    self.logger.warning(
                        "No image_generator configured — cover step will be skipped. "
                        "Set image_generator.enabled=true in config to enable."
                    )
                    return
                self.logger.warning(
                    "No image_generator configured — keeping existing cover background."
                )
            else:
                candidate_seeds = [1001, 2002, 3003, 4004, 5005, 6006, 7007, 8008]
                for i in range(1, candidate_count + 1):
                    candidate_path = (
                        bg_path if i == 1 else render_path(date, f"cover_bg_v{i}.png")
                    )
                    seed = candidate_seeds[(i - 1) % len(candidate_seeds)]
                    try:
                        self.image_generator.generate(
                            cover_prompt,
                            str(candidate_path),
                            aspect_ratio=cover_aspect_ratio,
                            seed=seed,
                        )
                    except (ValueError, RuntimeError, OSError) as e:
                        self.logger.warning(
                            f"Cover candidate {i} image generation failed "
                            f"({type(e).__name__}: {e})"
                        )
                        continue
                if candidate_count > 1:
                    self.logger.info(
                        f"  Generated {candidate_count} cover background candidates "
                        f"({bg_path.name} + cover_bg_v*.png); review and pick the best."
                    )

            if bg_path.exists():
                write_artifact_manifest(
                    bg_path,
                    step="cover_image",
                    date=date,
                    inputs=cover_bg_inputs,
                    config=self.config,
                )

        for i, variant in enumerate(variants[:COVER_VARIANT_COUNT], start=1):
            props = {
                "backgroundImage": bg_path.name,
                "title": variant["title"],
                "subtitle": variant["subtitle"],
                "tags": variant["tags"],
                "highlights": variant["highlights"],
                "dateLabel": date_label,
            }
            variant_path = render_path(date, f"cover_props_v{i}.json")
            atomic_write_json(variant_path, props)
            write_artifact_manifest(
                variant_path,
                step="cover_image",
                date=date,
                inputs={
                    "background": bg_path.name,
                    "variant_index": i,
                    "title_cover_variants_hash": variant_hash,
                    "cover_prompt_hash": cover_prompt_hash,
                },
                config=self.config,
            )

        self._mirror_cover_bg(date, bg_path)
        self.logger.info(
            f"  Cover image + {min(len(variants), COVER_VARIANT_COUNT)} variant(s) "
            f"written ({bg_path.name})"
        )

    def _load_title_cover_variants(self, date: str) -> list[dict[str, Any]]:
        title_path = publish_path(date, "title.json")
        if not title_path.exists():
            return []
        try:
            payload = json.loads(title_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        return _normalize_cover_variants(payload.get("cover_variants"))

    def _load_title_cover_prompt(self, date: str) -> str:
        title_path = publish_path(date, "title.json")
        if not title_path.exists():
            return ""
        try:
            payload = json.loads(title_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        return _normalize_cover_prompt(payload.get("cover_prompt"))

    def _mirror_cover_bg(self, date: str, bg_path: Path) -> None:
        """Mirror cover background into the per-date Remotion runtime dir."""
        public_bg = render_remotion_dir(date) / "public" / bg_path.name
        public_bg.parent.mkdir(parents=True, exist_ok=True)
        try:
            same_file = public_bg.samefile(bg_path)
        except FileNotFoundError:
            same_file = False
        if not same_file:
            shutil.copy2(bg_path, public_bg)
