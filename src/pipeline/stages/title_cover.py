"""Title metadata and cover-image stages."""

import json
import os
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
from src.pipeline.publish_copy import (
    TITLE_NORMALIZATION_VERSION,
    COVER_VARIANT_COUNT,
    _clean_publish_description,
    _downgrade_unsupported_publish_claims,
    _ensure_all_stories_in_description,
    _normalize_cover_variants,
    _preserve_source_uncertainty,
    _validate_title_grounding,
    _validate_title_payload,
)
from src.pipeline.stages.context import OrchestratorContext
from src.utils.atomic_io import atomic_write_json
from src.utils.text import normalize_cjk_mixed_spacing


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
