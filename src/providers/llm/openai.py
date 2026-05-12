import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from src.core.models import Script, ScriptSegment, SceneElement, ContentPackage, ContentItem, SelectionResult
from src.core.interfaces import LLMProvider
from src.core.prompts import render_prompt
from src.pipeline.comment_selection import clean_comment_text, compute_comment_quality, is_resource_pointer_comment
from src.pipeline.comment_judgement import normalize_story_judgement
from src.providers.llm.llm_client import (
    LLMClient,
    _strip_json_fence,
    _clamp_index_in_place,
    _floor_index_in_place,
)
from src.providers.llm.llm_cache import LLMCache


class OpenAILLMProvider(LLMProvider):
    def __init__(self, config: dict, debug: bool = False):
        self._client = LLMClient(config, debug=debug)
        # Expose key attributes for backward compatibility
        self.config = self._client.config
        self.debug = self._client.debug
        self.logger = self._client.logger
        self.client = self._client.client
        self.model = self._client.model
        self.max_tokens = self._client.max_tokens
        self.temperature = self._client.temperature
        self.fast_model = self._client.fast_model
        self.fast_max_tokens = self._client.fast_max_tokens
        self.fast_temperature = self._client.fast_temperature

        self._cache = LLMCache(self.logger, cache_schema_version=config.get("llm", {}).get("cache_schema_version", 2))
        self._total_stories = 0

    # ── Delegate LLM core calls ────────────────────────────────

    def _call_llm_with_json_retry(self, *args, **kwargs):
        return self._client.call_llm_with_json_retry(*args, **kwargs)

    def _extract_json(self, text: str) -> dict:
        return self._client.extract_json(text)

    @staticmethod
    def _split_prompt(prompt: str) -> List[Dict[str, str]]:
        return LLMClient.split_prompt(prompt)

    @staticmethod
    def _spinner(self, label: str):
        return self._client._spinner(label)

    # ── Segment Generation ─────────────────────────────────────

    def generate_single_story_segment(
        self,
        content: ContentPackage,
        story_index: int,
        segment_type: str,
        prompt_template_path: str,
        date: str,
        comments_data: Optional[Dict] = None
    ) -> ScriptSegment:
        item = content.items[story_index]
        story_json = self._single_story_to_json(item, story_index, comments_data=comments_data)

        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = prompt_template_path

        prompt = render_prompt(
            prompt_template,
            story_json=story_json,
            story_index=str(story_index),
            date=date
        )

        cache_meta = self._cache.build_segment_cache_meta(
            prompt=prompt,
            story_id=item.source_id,
            model=self.model,
            temperature=self.temperature,
        )

        cached = self._cache.load_cached_segment(
            date,
            segment_type,
            story_index,
            expected_cache_meta=cache_meta,
        )
        if cached is not None:
            self.logger.info(f"    [{segment_type}_{story_index}] Loaded from cache")
            return cached

        self.logger.info(f"    [{segment_type}_{story_index}] Generating...")

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label=f"{segment_type}_{story_index}"
        )

        seg_dict = self._extract_json(response_text)

        for elem in seg_dict.get("scene_elements", []):
            props = elem.get("props", {})
            _clamp_index_in_place(props, "story_index", len(content.items), f"{segment_type} scene_element", self.logger)
            _floor_index_in_place(props, "comment_index")

        scene_elements = [
            SceneElement(
                element_type=e["element_type"],
                start_time=0.0,
                end_time=0.0,
                props=e["props"]
            )
            for e in seg_dict.get("scene_elements", [])
        ]
        meta = seg_dict.get("meta", {})
        if "card_narrations" in seg_dict:
            meta["card_narrations"] = seg_dict["card_narrations"]
        if "debate_focus" in seg_dict:
            meta["debate_focus"] = seg_dict["debate_focus"]

        segment = ScriptSegment(
            segment_type=seg_dict.get("segment_type", segment_type),
            audio_text=seg_dict.get("audio_text", ""),
            estimated_duration=seg_dict.get("estimated_duration", 30.0),
            emotion=seg_dict.get("emotion", "neutral"),
            scene_elements=scene_elements,
            meta=meta,
        )

        self._cache.save_segment_cache(date, segment_type, story_index, segment, cache_meta=cache_meta)
        self.logger.info(f"    [{segment_type}_{story_index}] Done")
        return segment

    # ── Translation ────────────────────────────────────────────

    def translate_titles(self, content: ContentPackage, prompt_template: str) -> ContentPackage:
        items_to_translate = {}
        for idx, item in enumerate(content.items):
            if item.title:
                items_to_translate[f"title_{idx}"] = item.title

        if not items_to_translate:
            self.logger.info("  No titles to translate, skipping")
            return content

        prompt_path = Path("prompts") / prompt_template
        if prompt_path.exists():
            prompt_template_content = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template_content = prompt_template
        items_json = json.dumps(items_to_translate, ensure_ascii=False, indent=2)
        prompt = render_prompt(prompt_template_content, items_json=items_json)

        self.logger.info(f"  Translating {len(items_to_translate)} titles (model={self.fast_model})...")

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label="translate",
            max_tokens=self.fast_max_tokens,
            model=self.fast_model,
            temperature=self.fast_temperature,
        )

        result = self._extract_json(response_text)
        translations = result.get("translations", {})

        for key, value in translations.items():
            if key.startswith("title_"):
                idx = int(key.split("_", 1)[1])
                if idx < len(content.items):
                    content.items[idx].title_cn = value

        return content

    def translate_comments(self, content: ContentPackage, comment_refs: dict) -> dict:
        items_to_translate: dict = {}
        for key, value in comment_refs.items():
            if isinstance(value, str):
                items_to_translate[key] = value
            elif isinstance(value, list):
                if not isinstance(key, int):
                    continue
                if key >= len(content.items):
                    continue
                comments = content.items[key].comments
                for ci in value:
                    if ci < len(comments) and comments[ci].content:
                        items_to_translate[f"comment_{key}_{ci}"] = comments[ci].content

        if not items_to_translate:
            return {}

        prompt_path = Path("prompts/translate.md")
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = "translate.md"
        items_json = json.dumps(items_to_translate, ensure_ascii=False, indent=2)
        prompt = render_prompt(prompt_template, items_json=items_json)

        self.logger.info(
            f"  Translating {len(items_to_translate)} referenced comments "
            f"(model={self.fast_model})..."
        )

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label="translate_comments",
            max_tokens=max(self.fast_max_tokens, 8192),
            model=self.fast_model,
            temperature=self.fast_temperature,
        )

        result = self._extract_json(response_text)
        translations = result.get("translations", {})

        out = {}
        for key, value in translations.items():
            if key.startswith("comment_"):
                out[key] = value
        return out

    # ── Comment Judging ────────────────────────────────────────

    def judge_story_comments(
        self,
        item: ContentItem,
        story_index: int,
        prompt_template_path: str = "prompts/comment_analyze.md",
        candidates=None,
    ) -> dict:
        story_json = self._story_comments_for_judge(item, story_index, candidates=candidates)
        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = prompt_template_path
        prompt = render_prompt(prompt_template, story_json=story_json)

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label=f"comment_judge_{story_index}",
            max_tokens=self.config.get("analyze", {}).get("comment_judge_max_tokens", 512),
            model=self.fast_model,
            temperature=0.1,
            extra_body=self._comment_judge_extra_body(),
        )
        result = self._extract_json(response_text)
        return normalize_story_judgement(result, item)

    def _comment_judge_extra_body(self) -> Optional[Dict[str, Any]]:
        analyze_cfg = self.config.get("analyze", {})
        thinking = analyze_cfg.get("comment_judge_thinking", "disabled")
        if not thinking:
            return None
        return {"thinking": {"type": str(thinking)}}

    # ── Story Serialization ────────────────────────────────────

    def _single_story_to_json(self, item, index: int, comments_data: Optional[Dict] = None) -> str:
        analyze_cfg = self.config.get("analyze", {})
        min_quality = analyze_cfg.get("min_quality_score", 0.1)

        # When judge results are available, use quote_candidates to select comments.
        # Otherwise fall back to quality-score top-N selection.
        if comments_data and comments_data.get("quote_candidates"):
            candidate_ids = []
            for c in comments_data["quote_candidates"]:
                cid = c.get("comment_id")
                if cid is not None:
                    candidate_ids.append(str(cid))
            comments_by_id = {
                str(c.source_id): c
                for c in item.comments
                if c.source_id is not None
            }
            selected = []
            seen = set()
            for cid in candidate_ids:
                comment = comments_by_id.get(cid)
                if comment and cid not in seen:
                    selected.append(comment)
                    seen.add(cid)
            comments_json = []
            for c in selected:
                text = clean_comment_text(c.content)
                if not text:
                    continue
                comments_json.append({
                    "id": c.source_id,
                    "author": c.author,
                    "text": text,
                    "depth": c.depth,
                    "sentiment": c.sentiment,
                    "quality_score": c.quality_score,
                })
            self.logger.debug(
                f"Story[{index}] using {len(comments_json)} judge-selected comments "
                f"(from {len(candidate_ids)} candidates)"
            )
        else:
            max_comments = analyze_cfg.get(
                "max_comments_for_llm",
                self.config.get("pipeline", {}).get("max_comments_for_r1_analyze", 10),
            )
            scored_comments = []
            computed_fallback_scores = False
            for c in item.comments:
                text = clean_comment_text(c.content)
                if not text:
                    continue
                quality_score = c.quality_score
                if quality_score is None:
                    quality_score = compute_comment_quality(c, item)
                    c.quality_score = quality_score
                    computed_fallback_scores = True
                if quality_score >= min_quality:
                    scored_comments.append((quality_score, c, text))

            if not scored_comments:
                scored_comments = [
                    (compute_comment_quality(c, item), c, clean_comment_text(c.content))
                    for c in item.comments
                    if clean_comment_text(c.content)
                ]

            scored_comments.sort(key=lambda x: x[0], reverse=True)
            comments_json = [
                {
                    "id": c.source_id,
                    "author": c.author,
                    "text": text,
                    "depth": c.depth,
                    "sentiment": c.sentiment,
                    "quality_score": quality_score,
                }
                for quality_score, c, text in scored_comments[:max_comments]
            ]

            if computed_fallback_scores:
                self.logger.debug(
                    f"Story[{index}] comments had no analysis cache; "
                    f"computed fallback quality scores and selected top {len(comments_json)}"
                )

        story_dict = {
            "index": index,
            "id": item.source_id,
            "title": item.title,
            "url": item.url,
            "score": item.score,
            "comment_count": item.comment_count,
            "total_comments_available": len(item.comments),
            "truncated_to": len(comments_json),
            "comments": comments_json,
        }
        if item.article_summary:
            story_dict["article_summary"] = item.article_summary
        if item.article_text:
            story_dict["article_excerpt"] = item.article_text[:500]
        if item.article_images:
            story_dict["has_images"] = True
        if item.editor_angle:
            story_dict["editor_angle"] = item.editor_angle
        if item.dek:
            story_dict["dek"] = item.dek
        if item.key_points:
            story_dict["key_points"] = item.key_points
        if item.keywords:
            story_dict["keywords"] = item.keywords
        if item.category:
            story_dict["category"] = item.category
        if item.visual_hint:
            story_dict["visual_hint"] = item.visual_hint
        if comments_data:
            story_dict["comment_judgement"] = comments_data
        result = json.dumps(story_dict, ensure_ascii=False, indent=2)
        self.logger.debug(f"Story[{index}] serialized: {len(result)} chars ({story_dict['truncated_to']} comments)")
        return result

    def _story_comments_for_judge(self, item, index: int, candidates=None) -> str:
        if candidates is not None:
            comments_json = []
            for c in candidates:
                text = clean_comment_text(c.content or "")
                if not text or c.source_id is None:
                    continue
                comments_json.append({
                    "id": c.source_id,
                    "author": c.author,
                    "text": text[:360],
                    "depth": c.depth,
                    "sentiment": c.sentiment,
                    "quality_score": c.quality_score,
                    "resource_pointer_hint": is_resource_pointer_comment(text),
                })
            self.logger.debug(
                f"Story[{index}] judge using {len(comments_json)} "
                f"pre-filtered comments (from {len(candidates)} candidates)"
            )
        else:
            analyze_cfg = self.config.get("analyze", {})
            max_comments = analyze_cfg.get("max_comments_for_judge", 15)
            min_quality = analyze_cfg.get("judge_min_quality_score", 0.05)

            scored_comments = []
            for c in item.comments:
                text = clean_comment_text(c.content or "")
                if not text:
                    continue
                quality_score = c.quality_score
                if quality_score is None:
                    quality_score = compute_comment_quality(c, item)
                    c.quality_score = quality_score
                if quality_score < min_quality and not is_resource_pointer_comment(text):
                    continue
                scored_comments.append((quality_score, c, text))

            scored_comments.sort(
                key=lambda x: (
                    x[0],
                    -1 * (x[1].depth if x[1].depth is not None else 3),
                ),
                reverse=True,
            )
            comments_json = [
                {
                    "id": c.source_id,
                    "author": c.author,
                    "text": text[:360],
                    "depth": c.depth,
                    "sentiment": c.sentiment,
                    "quality_score": quality_score,
                    "resource_pointer_hint": is_resource_pointer_comment(text),
                }
                for quality_score, c, text in scored_comments[:max_comments]
                if c.source_id is not None
            ]

        story_dict = {
            "index": index,
            "id": item.source_id,
            "title": item.title,
            "url": item.url,
            "score": item.score,
            "comment_count": item.comment_count,
            "total_comments_available": len(item.comments),
            "truncated_to": len(comments_json),
            "comments": comments_json,
        }
        if item.article_summary:
            story_dict["article_summary"] = item.article_summary
        return json.dumps(story_dict, ensure_ascii=False, indent=2)
