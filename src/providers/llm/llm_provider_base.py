"""Shared LLM provider base for OpenAI-compatible and Anthropic transports.

Subclasses only need to declare which ``LLMClient`` class to instantiate. All
script generation, translation, comment judging, and prefilter logic lives
here, so the two transport adapters (``OpenAILLMProvider``, ``MiniMaxLLMProvider``)
stay small.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.models import (
    ContentItem,
    ContentPackage,
    SceneElement,
    ScriptSegment,
)
from src.core.interfaces import LLMProvider
from src.core.prompts import render_prompt
from src.pipeline.comment import (
    clean_comment_text,
    compute_comment_quality,
)
from src.pipeline.comment import normalize_story_judgement
from src.providers.llm.llm_cache import LLMCache
from src.providers.llm.llm_client import (
    LLMClient,
    _clamp_index_in_place,
    _floor_index_in_place,
)

_TEMPLATE_CACHE: Dict[str, tuple[float, str]] = {}
_SUBTITLE_PUNCTUATION = "\u3002\uff01\uff1f.!?"


def _with_sentence_punctuation(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in _SUBTITLE_PUNCTUATION:
        return text + "\u3002"
    return text


def _normalize_card_narration_subtitles(cards: list) -> None:
    for card in cards:
        if not isinstance(card, dict):
            continue
        texts = card.get("subtitle_texts") or []
        normalized_texts: List[str] = []
        if isinstance(texts, list):
            for text in texts:
                if isinstance(text, str):
                    stripped = text.strip()
                    if stripped:
                        normalized_texts.append(_with_sentence_punctuation(stripped))
        card["subtitle_texts"] = normalized_texts


def _read_template_cached(path: str) -> str:
    """Read a prompt template from disk, caching in memory with mtime-based invalidation.

    Prompt templates change during development. The first read stores
    ``(mtime, content)``; subsequent reads re-stat the file and re-read on
    change, so a hot-reload after editing ``prompts/*.md`` "just works" within
    a long-running pipeline. Tests can call :func:`_clear_template_cache` to
    reset state between cases.
    """
    p = Path(path)
    try:
        current_mtime = p.stat().st_mtime
    except OSError:
        return p.read_text(encoding="utf-8")

    cached = _TEMPLATE_CACHE.get(path)
    if cached is None or cached[0] != current_mtime:
        _TEMPLATE_CACHE[path] = (current_mtime, p.read_text(encoding="utf-8"))
    return _TEMPLATE_CACHE[path][1]


def _clear_template_cache() -> None:
    """Clear the in-process template cache. Intended for tests."""
    _TEMPLATE_CACHE.clear()


def _build_card_narration_validator(expected_card_types: List[str], logger):
    """Validate the LLM's segment JSON against the tier's card schema.

    Raising ValueError triggers a re-prompt inside call_llm_with_json_retry.
    Empty card_narrations is accepted (downstream fallback handles it).
    """
    expected_set = set(expected_card_types)

    def _validate(parsed: dict) -> None:
        cards = parsed.get("card_narrations") or []
        if not cards:
            # Accept empty: _process_story_narrations has a fallback path.
            logger.warning(
                "LLM returned empty card_narrations (expected %s); "
                "downstream will fall back to audio_text",
                expected_card_types,
            )
            return
        for i, card in enumerate(cards):
            if not isinstance(card, dict):
                raise ValueError(f"card_narrations[{i}] is not an object")
            ct = card.get("card_type")
            if ct not in expected_set:
                raise ValueError(
                    f"card_narrations[{i}].card_type={ct!r} is missing or "
                    f"not one of {expected_card_types}"
                )
            texts = card.get("subtitle_texts") or []
            if not isinstance(texts, list) or not any(
                isinstance(t, str) and t.strip() for t in texts
            ):
                raise ValueError(
                    f"card_narrations[{i}].subtitle_texts must be a non-empty list of strings"
                )
            _normalize_card_narration_subtitles([card])
            for j, text in enumerate(card["subtitle_texts"]):
                if not isinstance(text, str):
                    raise ValueError(
                        f"card_narrations[{i}].subtitle_texts[{j}] must be a string"
                    )
                stripped = text.strip()
                if stripped and stripped[-1] not in _SUBTITLE_PUNCTUATION:
                    raise ValueError(
                        f"card_narrations[{i}].subtitle_texts[{j}] must end with punctuation"
                    )

    return _validate


class LLMProviderBase(LLMProvider):
    """Transport-agnostic implementation of the LLMProvider ABC.

    Subclasses set ``llm_client_class`` to pick the right transport:
    ``LLMClient`` for OpenAI-compatible, ``AnthropicLLMClient`` for Anthropic.
    """

    llm_client_class: type = LLMClient

    def __init__(self, config: dict, debug: bool = False):
        self._client = self.llm_client_class(config, debug=debug)
        self._cache = LLMCache(
            self._client.logger,
            cache_schema_version=config.get("llm", {}).get("cache_schema_version", 2),
        )

    @property
    def config(self) -> dict:
        return self._client.config

    @property
    def debug(self) -> bool:
        return self._client.debug

    @property
    def logger(self):
        return self._client.logger

    @property
    def client(self):
        return self._client.client

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def max_tokens(self) -> int:
        return self._client.max_tokens

    @property
    def temperature(self) -> float:
        return self._client.temperature

    @property
    def fast_model(self) -> str:
        return self._client.fast_model

    @property
    def fast_max_tokens(self) -> int:
        return self._client.fast_max_tokens

    @property
    def fast_temperature(self) -> float:
        return self._client.fast_temperature

    @property
    def llm_client(self) -> LLMClient:
        """Public accessor for the underlying transport client."""
        return self._client

    # Delegate LLM core calls

    def _call_llm_with_json_retry(self, *args, **kwargs):
        return self._client.call_llm_with_json_retry(*args, **kwargs)

    def _extract_json(self, text: str) -> dict:
        return self._client.extract_json(text)

    @staticmethod
    def _split_prompt(prompt: str) -> List[Dict[str, str]]:
        return LLMClient.split_prompt(prompt)

    def complete_prompt(
        self,
        prompt_template_path: str,
        context: Dict[str, str],
        label: str,
        expect_json: bool = True,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        """Render a prompt template and call the LLM.

        Returns the parsed dict when expect_json=True (via
        :meth:`_call_llm_with_json_retry`); returns raw text otherwise
        (single-shot, no JSON retry loop; caller controls the output shape).

        ``model`` and ``temperature`` default to the main transport config;
        pass ``self.fast_model`` for simple JSON/markdown one-shots to avoid
        paying the main-model cost.

        Centralized helper for pipeline steps that need a one-shot LLM call
        (title generation, cover prompt, publish guide) without inheriting
        the ceremony of :meth:`generate_single_story_segment`.
        """
        template = _read_template_cached(prompt_template_path)
        rendered = render_prompt(template, **context)
        messages = self._split_prompt(rendered)
        if expect_json:
            text = self._call_llm_with_json_retry(
                messages=messages,
                label=label,
                max_tokens=max_tokens,
                model=model,
                temperature=temperature,
            )
            return self._extract_json(text)
        return self._client.call_llm_text(
            messages=messages,
            label=label,
            max_tokens=max_tokens,
            model=model,
            temperature=temperature,
        )

    def _spinner(self, label: str):
        return self._client._spinner(label)

    # Segment Generation

    def generate_single_story_segment(
        self,
        content: ContentPackage,
        story_index: int,
        segment_type: str,
        prompt_template_path: str,
        date: str,
        comments_data: Optional[Dict] = None,
        expected_card_types: Optional[List[str]] = None,
    ) -> ScriptSegment:
        item = content.items[story_index]
        story_json = self._single_story_to_json(
            item, story_index, comments_data=comments_data
        )

        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = _read_template_cached(str(prompt_path))
        else:
            prompt_template = prompt_template_path

        prompt = render_prompt(
            prompt_template,
            story_json=story_json,
            story_index=str(story_index),
            date=date,
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

        validator = (
            _build_card_narration_validator(expected_card_types, self.logger)
            if expected_card_types
            else None
        )

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label=f"{segment_type}_{story_index}",
            validator=validator,
        )

        seg_dict = self._extract_json(response_text)
        _normalize_card_narration_subtitles(seg_dict.get("card_narrations") or [])

        for elem in seg_dict.get("scene_elements", []):
            props = elem.get("props", {})
            _clamp_index_in_place(
                props,
                "story_index",
                len(content.items),
                f"{segment_type} scene_element",
                self.logger,
            )
            _floor_index_in_place(props, "comment_index")

        scene_elements = [
            SceneElement(
                element_type=e["element_type"],
                start_time=e.get("start_time", 0.0),
                end_time=e.get("end_time", 0.0),
                props=e["props"],
                sub_segment_index=e.get("sub_segment_index"),
            )
            for e in seg_dict.get("scene_elements", [])
        ]
        meta = seg_dict.get("meta", {})
        if "card_narrations" in seg_dict:
            meta["card_narrations"] = seg_dict["card_narrations"]
        if "debate_focus" in seg_dict:
            meta["debate_focus"] = seg_dict["debate_focus"]
        if "signal" in seg_dict:
            meta["signal"] = seg_dict["signal"]

        segment = ScriptSegment(
            segment_type=seg_dict.get("segment_type", segment_type),
            audio_text=seg_dict.get("audio_text", ""),
            duration=seg_dict.get("duration", seg_dict.get("estimated_duration", 0.0)),
            scene_elements=scene_elements,
            meta=meta,
        )

        self._cache.save_segment_cache(
            date, segment_type, story_index, segment, cache_meta=cache_meta
        )
        self.logger.info(f"    [{segment_type}_{story_index}] Done")
        return segment

    # Translation

    def translate_titles(
        self, content: ContentPackage, prompt_template: str, date: str = ""
    ) -> ContentPackage:
        items_to_translate: Dict[str, str] = {}
        items_by_key: Dict[str, Any] = {}
        for item in content.items:
            if item.title and item.source_id:
                key = f"title_{item.source_id}"
                items_to_translate[key] = item.title
                items_by_key[key] = item

        if not items_to_translate:
            self.logger.info("  No titles to translate, skipping")
            return content

        prompt_path = Path("prompts") / prompt_template
        if prompt_path.exists():
            prompt_template_content = _read_template_cached(str(prompt_path))
        else:
            prompt_template_content = prompt_template
        items_json = json.dumps(items_to_translate, ensure_ascii=False, indent=2)
        prompt = render_prompt(prompt_template_content, items_json=items_json)

        cache_meta = self._cache.build_cache_meta(
            prompt=prompt,
            model=self.fast_model,
            temperature=self.fast_temperature,
        )

        if date:
            cached = self._cache.load_dict_cache(
                date, "titles", expected_cache_meta=cache_meta
            )
            if cached is not None:
                for key, value in cached.items():
                    item = items_by_key.get(key)
                    if item is not None:
                        item.title_cn = value
                self.logger.info(f"  Titles loaded from cache ({len(cached)} items)")
                return content

        self.logger.info(
            f"  Translating {len(items_to_translate)} titles (model={self.fast_model})..."
        )

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
                item = items_by_key.get(key)
                if item is not None:
                    item.title_cn = value

        if date and translations:
            self._cache.save_dict_cache(
                date, "titles", translations, cache_meta=cache_meta
            )

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
            prompt_template = _read_template_cached(str(prompt_path))
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

    # Comment Judging

    def judge_story_comments(
        self,
        item: ContentItem,
        story_index: int,
        prompt_template_path: str = "prompts/comment_analyze.md",
        candidates=None,
    ) -> dict:
        story_json = LLMClient.story_comments_for_judge(
            item, story_index, self.config, self.logger, candidates=candidates
        )
        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = _read_template_cached(str(prompt_path))
        else:
            prompt_template = prompt_template_path
        prompt = render_prompt(prompt_template, story_json=story_json)

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label=f"comment_judge_{story_index}",
            max_tokens=self.config.get("analyze", {}).get(
                "comment_judge_max_tokens", 512
            ),
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

    # Prefilter

    def prefilter_stories(
        self,
        stories: list,
        prompt_template_path: str = "prompts/prefilter.md",
    ) -> list:
        stories_json = json.dumps(
            [
                {
                    "index": story[0],
                    "title": story[1],
                    "url": story[2],
                    "score": story[3] if len(story) > 4 else None,
                    "comment_count": story[4] if len(story) > 4 else None,
                    "comments": story[5] if len(story) > 5 else story[3],
                }
                for story in stories
            ],
            ensure_ascii=False,
            indent=2,
        )
        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = _read_template_cached(str(prompt_path))
        else:
            prompt_template = prompt_template_path
        prompt = render_prompt(prompt_template, stories_json=stories_json)

        prefilter_cfg = self.config.get("prefilter", {})
        temperature = prefilter_cfg.get("temperature", 0.1)

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label="prefilter",
            max_tokens=self.fast_max_tokens,
            model=self.fast_model,
            temperature=temperature,
        )
        result = self._extract_json(response_text)
        return result.get("decisions", [])

    def prefilter_single_story(
        self,
        story: tuple,
        prompt_template_path: str = "prompts/prefilter.md",
    ) -> dict:
        """Score a single story independently (no cross-story context pollution)."""
        decisions = self.prefilter_stories([story], prompt_template_path)
        if decisions:
            return decisions[0]
        return {"keep": True, "reason": "no LLM response"}

    # Story Serialization

    def _single_story_to_json(
        self, item, index: int, comments_data: Optional[Dict] = None
    ) -> str:
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
                str(c.source_id): c for c in item.comments if c.source_id is not None
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
                comments_json.append(
                    {
                        "id": c.source_id,
                        "author": c.author,
                        "text": text,
                        "depth": c.depth,
                        "sentiment": c.sentiment,
                        "quality_score": c.quality_score,
                    }
                )
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
        if comments_data:
            story_dict["comment_judgement"] = comments_data
            story_dict["discussion_mode"] = comments_data.get("discussion_mode")
            story_dict["discussion_summary"] = comments_data.get("discussion_summary")
            story_dict["comment_lanes"] = comments_data.get("comment_lanes")
        result = json.dumps(story_dict, ensure_ascii=False, indent=2)
        self.logger.debug(
            f"Story[{index}] serialized: {len(result)} chars ({story_dict['truncated_to']} comments)"
        )
        return result

