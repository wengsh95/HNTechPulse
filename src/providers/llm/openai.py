import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
import threading
from contextlib import contextmanager

from openai import OpenAI
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models import Script, ScriptSegment, SceneElement, Cue, ContentPackage, SelectionResult
from src.core.interfaces import LLMProvider
from src.core.prompts import render_prompt
from src.utils.logger import setup_logger
from src.utils.config import get_env


_JSON_FENCE_START_RE = re.compile(r'^```(?:json)?\s*\n?')
_JSON_FENCE_END_RE = re.compile(r'\n?```\s*$')


def _strip_json_fence(text: str) -> str:
    """Remove leading/trailing markdown code fences around JSON payloads.

    Handles ```json ... ``` and ``` ... ``` wrappers that LLMs sometimes emit
    around JSON responses. Safe to call on already-clean text.
    """
    text = text.strip()
    text = _JSON_FENCE_START_RE.sub('', text)
    text = _JSON_FENCE_END_RE.sub('', text)
    return text.strip()


def _deep_dive_comment_indices(dd: dict) -> List[int]:
    """Return sorted unique comment indices referenced by a deep_dive_decision.

    Combines `featured_comment_indices` with `perspective_a.comment_index` and
    `perspective_b.comment_index`. Missing/None values are skipped.
    """
    indices = set(dd.get("featured_comment_indices", []) or [])
    for key in ("perspective_a", "perspective_b"):
        ci = (dd.get(key) or {}).get("comment_index")
        if ci is not None:
            indices.add(ci)
    return sorted(indices)


def _iter_story_comment_selections(
    selection: "SelectionResult",
) -> Iterator[Tuple[str, int, List[int]]]:
    """Yield (category, story_index, comment_indices) for every selected story.

    `category` is one of "deep_dive", "medium", "quick".
    `comment_indices` is:
      - for deep_dive: sorted featured + perspective_a/b indices (may be empty)
      - for medium/quick: [featured_comment_index] or [] when missing

    Entries with no `story_index` are skipped. Bounds vs `content.items` are
    NOT checked here; callers that index into content must guard themselves.
    """
    dd = selection.deep_dive_decision
    dd_idx = dd.get("story_index")
    if dd_idx is not None:
        yield "deep_dive", dd_idx, _deep_dive_comment_indices(dd)

    for mi in getattr(selection, "medium_selections", []):
        idx = mi.get("story_index")
        if idx is None:
            continue
        fc = mi.get("featured_comment_index")
        yield "medium", idx, [fc] if fc is not None else []

    for qi in selection.quick_selections:
        idx = qi.get("story_index")
        if idx is None:
            continue
        fc = qi.get("featured_comment_index")
        yield "quick", idx, [fc] if fc is not None else []


def _clamp_index_in_place(d: dict, key: str, max_val: int, label: str, logger=None) -> None:
    """If d[key] is an int outside [0, max_val), clamp it in place and warn.

    Non-int / None / in-range values are left untouched.
    """
    v = d.get(key)
    if not isinstance(v, int):
        return
    if v < 0 or v >= max_val:
        if logger is not None:
            logger.info(f"  {label} {key}={v} out of range [0,{max_val}), clamping")
        d[key] = max(0, min(v, max_val - 1))


def _floor_index_in_place(d: dict, key: str) -> None:
    """If d[key] is a negative int, floor it to 0. No-op for None/non-int/non-negative."""
    v = d.get(key)
    if isinstance(v, int) and v < 0:
        d[key] = 0




class OpenAILLMProvider(LLMProvider):
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        api_key = get_env("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        base_url = config.get("llm", {}).get("base_url") or get_env("OPENAI_BASE_URL")
        if base_url:
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=10.0),
            )
            self.logger.info(f"Using OpenAI-compatible API at: {base_url}")
        else:
            self.client = OpenAI(
                api_key=api_key,
                timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=10.0),
            )

        llm_cfg = config.get("llm", {})
        self.model = llm_cfg.get("model", "gpt-4o")
        self.max_tokens = llm_cfg.get("max_tokens", 8192)
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.json_parse_max_retries = llm_cfg.get("json_parse_max_retries", 3)

        fast_cfg = llm_cfg.get("fast", {})
        self.fast_model = fast_cfg.get("model", self.model)
        self.fast_max_tokens = fast_cfg.get("max_tokens", 4096)
        self.fast_temperature = fast_cfg.get("temperature", 0.3)

        self._total_stories = 0

    def _call_llm_with_json_retry(
        self,
        messages: List[Dict[str, str]],
        label: str,
        max_tokens: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        current_messages = list(messages)
        effective_max_tokens = max_tokens or self.max_tokens
        effective_model = model or self.model
        effective_temperature = temperature if temperature is not None else self.temperature

        for attempt in range(1, self.json_parse_max_retries + 1):
            t0 = time.monotonic()

            with self._spinner(f"[{label}] API response pending (attempt {attempt})..."):
                response = self.client.chat.completions.create(
                    model=effective_model,
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature,
                    messages=current_messages
                )
            elapsed = time.monotonic() - t0

            response_text = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
            usage = response.usage

            details = getattr(usage, "prompt_tokens_details", None)
            cached = getattr(details, "cached_tokens", 0) if details else 0
            if not cached:
                cached = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
            miss = usage.prompt_tokens - cached
            hit_pct = (cached / usage.prompt_tokens * 100) if usage.prompt_tokens else 0

            self.logger.info(
                f"  [{label}] Done in {elapsed:.1f}s "
                f"(prompt={usage.prompt_tokens} [cache hit={cached}/{hit_pct:.0f}%, miss={miss}], "
                f"completion={usage.completion_tokens}, total={usage.total_tokens} tokens, attempt={attempt})"
            )

            if finish_reason == "length":
                self.logger.info(
                    f"  [{label}] Response truncated (finish_reason=length, "
                    f"completion={usage.completion_tokens}/{effective_max_tokens} tokens). "
                    f"Doubling max_tokens and retrying..."
                )
                effective_max_tokens = min(effective_max_tokens * 2, 32768)
                continue

            try:
                self._extract_json(response_text)
                return response_text
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.info(
                    f"  [{label}] JSON parse failed on attempt {attempt}/{self.json_parse_max_retries}: {e}"
                )
                if attempt < self.json_parse_max_retries:
                    error_feedback = (
                        f"\n\n---\nYour previous response contained invalid JSON:\n"
                        f"Error: {e}\n\n"
                        f"Please fix the JSON and respond again with valid JSON only. "
                        f"Common issues: trailing commas, unquoted keys, missing commas, "
                        f"or text outside the JSON structure. "
                        f"Output ONLY the JSON object, no markdown fences or extra text."
                    )
                    current_messages = list(messages) + [
                        {"role": "assistant", "content": response_text},
                        {"role": "user", "content": error_feedback}
                    ]
                    self.logger.info(f"  [{label}] Re-requesting with error feedback...")
                else:
                    self.logger.error(
                        f"  [{label}] JSON parse failed after {self.json_parse_max_retries} attempts"
                    )
                    raise

        raise ValueError(f"[{label}] Failed to get valid JSON after {self.json_parse_max_retries} retries")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry_error_callback=lambda retry_state: retry_state.outcome.result())
    def generate_script(
        self,
        selection: SelectionResult,
        comments_json: str,
        script_prompt_template: str,
        date: str,
    ) -> Script:
        self.logger.info("  Round 2: Generating script...")

        prompt = render_prompt(
            script_prompt_template,
            selection_json=selection.raw_json,
            comments_json=comments_json,
            date=date,
        )

        self.logger.info(f"    Input: selection={len(selection.raw_json)} chars, comments={len(comments_json)} chars")

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label="R2"
        )

        script_dict = self._extract_json(response_text)
        # 校验 scene_elements 中的 story_index / comment_index 越界
        self._validate_script_indices(script_dict, self._total_stories)
        script = self._dict_to_script(script_dict)

        self._validate_script_quality(script)
        self._log_script_preview(script)
        return script

    def _get_segment_cache_path(self, date: str, segment_type: str, story_index: int) -> Path:
        """获取单个 segment 的缓存文件路径"""
        cache_dir = Path(f"data/{date}/segments")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{segment_type}_{story_index}.json"

    def _load_cached_segment(self, date: str, segment_type: str, story_index: int) -> Optional[ScriptSegment]:
        """加载缓存的 segment"""
        cache_path = self._get_segment_cache_path(date, segment_type, story_index)
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                seg_dict = json.load(f)
            # 重建 ScriptSegment 对象
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
                    end_time=c["end_time"]
                )
                for c in seg_dict.get("cues", [])
            ]
            return ScriptSegment(
                segment_type=seg_dict["segment_type"],
                audio_text=seg_dict["audio_text"],
                estimated_duration=seg_dict["estimated_duration"],
                emotion=seg_dict.get("emotion", "neutral"),
                scene_elements=scene_elements,
                meta=seg_dict.get("meta", {}),
                cues=cues
            )
        except Exception as e:
            self.logger.warning(f"    Failed to load cached segment: {e}")
            return None

    def _save_segment_cache(self, date: str, segment_type: str, story_index: int, segment: ScriptSegment) -> None:
        """保存 segment 到缓存"""
        cache_path = self._get_segment_cache_path(date, segment_type, story_index)
        seg_dict = {
            "segment_type": segment.segment_type,
            "audio_text": segment.audio_text,
            "estimated_duration": segment.estimated_duration,
            "emotion": segment.emotion,
            "scene_elements": [
                {
                    "element_type": e.element_type,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "props": e.props
                }
                for e in segment.scene_elements
            ],
            "cues": [
                {
                    "text": c.text,
                    "start_time": c.start_time,
                    "end_time": c.end_time
                }
                for c in segment.cues
            ],
            "meta": segment.meta
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(seg_dict, f, ensure_ascii=False, indent=2)

    def generate_single_story_segment(
        self,
        content: ContentPackage,
        story_index: int,
        segment_type: str,
        prompt_template_path: str,
        date: str,
        comments_data: Optional[Dict] = None
    ) -> ScriptSegment:
        """为单个 story 生成对应的 ScriptSegment，带缓存"""
        # 先尝试从缓存加载
        cached = self._load_cached_segment(date, segment_type, story_index)
        if cached is not None:
            self.logger.info(f"    [{segment_type}_{story_index}] Loaded from cache")
            return cached

        self.logger.info(f"    [{segment_type}_{story_index}] Generating...")

        # 准备输入数据
        item = content.items[story_index]
        story_json = self._single_story_to_json(item, story_index)

        # 加载提示词模板
        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = prompt_template_path

        # 准备 comments_json（如果有）
        comments_json_str = "{}"
        if comments_data:
            comments_json_str = json.dumps(comments_data, ensure_ascii=False, indent=2)

        # 渲染提示词
        prompt = render_prompt(
            prompt_template,
            story_json=story_json,
            story_index=str(story_index),
            comments_json=comments_json_str,
            date=date
        )

        # 调用 LLM
        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label=f"{segment_type}_{story_index}"
        )

        # 解析结果
        seg_dict = self._extract_json(response_text)

        # 校验索引越界
        for elem in seg_dict.get("scene_elements", []):
            props = elem.get("props", {})
            _clamp_index_in_place(props, "story_index", len(content.items), f"{segment_type} scene_element", self.logger)
            _floor_index_in_place(props, "comment_index")

        # 构建 ScriptSegment
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
                end_time=c["end_time"]
            )
            for c in seg_dict.get("cues", [])
        ]
        segment = ScriptSegment(
            segment_type=seg_dict.get("segment_type", segment_type),
            audio_text=seg_dict.get("audio_text", ""),
            estimated_duration=seg_dict.get("estimated_duration", 30.0),
            emotion=seg_dict.get("emotion", "neutral"),
            scene_elements=scene_elements,
            meta=seg_dict.get("meta", {}),
            cues=cues
        )

        # 保存缓存
        self._save_segment_cache(date, segment_type, story_index, segment)
        self.logger.info(f"    [{segment_type}_{story_index}] Done")
        return segment

    @contextmanager
    def _spinner(self, label: str):
        t0 = time.monotonic()
        stop_event = threading.Event()

        def _animate():
            symbols = "⠋⠙⠹⠸⠼⠴⠦⠧⠏"
            i = 0
            while not stop_event.is_set():
                elapsed_sec = int(time.monotonic() - t0)
                line = f"  {symbols[i % len(symbols)]} {label} elapsed {elapsed_sec}s"
                print(line, end="\r", flush=True)
                time.sleep(0.5)
                i += 1
            print(" " * 80, end="\r", flush=True)

        thread = threading.Thread(target=_animate, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=2.0)

    def _log_script_preview(self, script: Script) -> None:
        for i, seg in enumerate(script.segments):
            text_preview = seg.audio_text[:60].replace("\n", " ")
            self.logger.info(
                f"    [{i}] [{seg.segment_type}] ({seg.estimated_duration}s) '{text_preview}{'...' if len(seg.audio_text) > 60 else ''}'"
            )
        self.logger.info(f"  Round 2 complete: {len(script.segments)} segments")

    def _validate_script_quality(self, script: Script) -> None:
        """Log warnings for script segments that don't meet content minimums."""
        MIN_CHARS = {
            "deep_dive": 250,
            "medium_dive": 120,
        }
        for i, seg in enumerate(script.segments):
            min_c = MIN_CHARS.get(seg.segment_type)
            if min_c and len(seg.audio_text) < min_c:
                self.logger.info(
                    f"  Quality check: segment {i} [{seg.segment_type}] "
                    f"audio_text only {len(seg.audio_text)} chars "
                    f"(minimum {min_c})"
                )

        for seg in script.segments:
            if seg.segment_type == "quick_news":
                qi = seg.meta.get("quick_items", [])
                if len(qi) > 4:
                    self.logger.info(
                        f"  Quality check: quick_news has {len(qi)} items (max 4)"
                    )
                for item in qi:
                    summary = item.get("summary", "")
                    if len(summary) < 40:
                        self.logger.info(
                            f"  Quality check: quick_news item story_index={item.get('story_index')} "
                            f"summary only {len(summary)} chars (min 60 recommended)"
                        )

    def _single_story_to_json(self, item, index: int) -> str:
        pipeline_cfg = self.config.get("pipeline", {})
        max_comments = pipeline_cfg.get("max_comments_for_r1_analyze", 80)

        story_dict = {
            "index": index,
            "id": item.source_id,
            "title": item.title,
            "url": item.url,
            "score": item.score,
            "comment_count": item.comment_count,
            "total_comments_available": len(item.comments),
            "truncated_to": min(len(item.comments), max_comments),
            "comments": [
                {"author": c.author, "text": c.content}
                for c in item.comments[:max_comments]
            ]
        }
        # Add enrichment data if available
        if item.article_summary:
            story_dict["article_summary"] = item.article_summary
        if item.article_text:
            story_dict["article_excerpt"] = item.article_text[:500]
        if item.article_images:
            story_dict["has_images"] = True
        result = json.dumps(story_dict, ensure_ascii=False, indent=2)
        self.logger.debug(f"Story[{index}] serialized: {len(result)} chars ({story_dict['truncated_to']} comments)")
        return result

    def _build_short_item_json(self, item, fc_idx) -> dict:
        """Build the per-story dict used for medium_items / quick_items entries."""
        comment_data = None
        if fc_idx is not None and fc_idx < len(item.comments):
            c = item.comments[fc_idx]
            comment_data = {
                "comment_index_in_story": fc_idx,
                "author": c.author,
                "text": c.content,
                "text_cn": c.content_cn,
            }
        d = {
            "story_title": item.title,
            "story_title_cn": item.title_cn,
            "story_score": item.score,
            "story_comment_count": item.comment_count,
            "featured_comment": comment_data,
        }
        if item.article_summary:
            d["article_summary"] = item.article_summary
        if item.article_images:
            d["has_images"] = True
        return d

    def build_comments_json(
        self,
        content: ContentPackage,
        selection: SelectionResult
    ) -> str:
        result = {"deep_dive": {}, "medium_items": {}, "quick_items": {}}

        dd = selection.deep_dive_decision
        di_idx = dd.get("story_index")
        if di_idx is not None and di_idx < len(content.items):
            item = content.items[di_idx]
            sorted_indices = _deep_dive_comment_indices(dd)
            result["deep_dive"] = {
                "story_index": di_idx,
                "story_title": item.title,
                "story_title_cn": item.title_cn,
                "story_score": item.score,
                "story_comment_count": item.comment_count,
                "comments": [
                    {
                        "comment_index_in_story": ci,
                        "author": item.comments[ci].author,
                        "text": item.comments[ci].content,
                        "text_cn": item.comments[ci].content_cn,
                    }
                    for ci in sorted_indices if ci < len(item.comments)
                ]
            }
            if item.article_summary:
                result["deep_dive"]["article_summary"] = item.article_summary
            if item.article_images:
                result["deep_dive"]["has_images"] = True

        for mi in getattr(selection, "medium_selections", []):
            mi_idx = mi.get("story_index")
            if mi_idx is not None and mi_idx < len(content.items):
                result["medium_items"][str(mi_idx)] = self._build_short_item_json(
                    content.items[mi_idx], mi.get("featured_comment_index")
                )

        for qi in selection.quick_selections:
            qi_idx = qi.get("story_index")
            if qi_idx is not None and qi_idx < len(content.items):
                result["quick_items"][str(qi_idx)] = self._build_short_item_json(
                    content.items[qi_idx], qi.get("featured_comment_index")
                )

        pattern_evidence = []
        for p in selection.patterns:
            for ev in p.get("evidence", []):
                si = ev.get("story_index")
                ci = ev.get("comment_index")
                if si is not None and si < len(content.items):
                    item = content.items[si]
                    if ci is not None and ci < len(item.comments):
                        c = item.comments[ci]
                        pattern_evidence.append({
                            "pattern_name": p.get("name"),
                            "story_index": si,
                            "story_title": item.title,
                            "comment_index": ci,
                            "author": c.author,
                            "text": c.content,
                            "quote_summary": ev.get("summary", "")
                        })

        result["pattern_evidence"] = pattern_evidence
        output = json.dumps(result, ensure_ascii=False, indent=2)
        self.logger.info(
            f"Built comments JSON: deep={len(result['deep_dive'].get('comments', []))}, "
            f"medium={len(result['medium_items'])}, quick={len(result['quick_items'])}, "
            f"evidence={len(pattern_evidence)}, total={len(output)} chars"
        )
        return output

    def _collect_selected_indices(self, selection: SelectionResult) -> set:
        return {story_idx for _, story_idx, _ in _iter_story_comment_selections(selection)}

    def _collect_selected_comment_indices(self, content: ContentPackage, selection: SelectionResult) -> Dict[int, List[int]]:
        """Map story_index -> list of comment indices to translate."""
        comment_map: Dict[int, List[int]] = {}

        for category, story_idx, comment_indices in _iter_story_comment_selections(selection):
            if category == "deep_dive":
                # Preserve original behavior: always set the key for deep_dive
                # (even with empty list) once the story_index is in bounds.
                if story_idx < len(content.items):
                    comment_map[story_idx] = list(comment_indices)
            else:
                # medium / quick: upsert only when a comment index is present
                for ci in comment_indices:
                    existing = comment_map.setdefault(story_idx, [])
                    if ci not in existing:
                        existing.append(ci)

        return comment_map

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10),
           retry_error_callback=lambda retry_state: retry_state.outcome.result())
    def translate_selection(
        self,
        content: ContentPackage,
        selection: SelectionResult,
        prompt_template: str
    ) -> ContentPackage:
        date = content.date
        translations_path = Path(f"data/{date}/translations.json")

        # Checkpoint: load existing translations
        if translations_path.exists():
            self.logger.info(f"  Found existing {translations_path}, loading translations")
            with open(translations_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            self._apply_translations(content, cached)
            return content

        selected_indices = self._collect_selected_indices(selection)
        comment_map = self._collect_selected_comment_indices(content, selection)

        # Build items to translate
        items_to_translate = {}
        for idx in sorted(selected_indices):
            if idx >= len(content.items):
                continue
            item = content.items[idx]
            items_to_translate[f"title_{idx}"] = item.title
            for ci in comment_map.get(idx, []):
                if ci < len(item.comments):
                    items_to_translate[f"comment_{idx}_{ci}"] = item.comments[ci].content

        if not items_to_translate:
            self.logger.info("  No items to translate, skipping")
            return content

        items_json = json.dumps(items_to_translate, ensure_ascii=False, indent=2)
        prompt = render_prompt(prompt_template, items_json=items_json)

        self.logger.info(f"  Translating {len(items_to_translate)} items (titles + comments)...")

        response_text = self._call_llm_with_json_retry(
            messages=self._split_prompt(prompt),
            label="translate",
            max_tokens=min(self.max_tokens, 4096)
        )

        result = self._extract_json(response_text)
        translations = result.get("translations", {})

        # Save checkpoint
        translations_path.parent.mkdir(parents=True, exist_ok=True)
        with open(translations_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)
        self.logger.info(f"  Saved translations to {translations_path}")

        self._apply_translations(content, translations)
        return content

    @staticmethod
    def _apply_translations(content: ContentPackage, translations: dict) -> None:
        for key, value in translations.items():
            if key.startswith("title_"):
                idx = int(key.split("_", 1)[1])
                if idx < len(content.items):
                    content.items[idx].title_cn = value
            elif key.startswith("comment_"):
                parts = key.split("_")
                if len(parts) == 3:
                    idx, ci = int(parts[1]), int(parts[2])
                    if idx < len(content.items) and ci < len(content.items[idx].comments):
                        content.items[idx].comments[ci].content_cn = value

    def translate_titles(self, content: ContentPackage, prompt_template: str) -> ContentPackage:
        """Translate all story titles using the fast/cheap model."""
        items_to_translate = {}
        for idx, item in enumerate(content.items):
            if item.title:
                items_to_translate[f"title_{idx}"] = item.title

        if not items_to_translate:
            self.logger.info("  No titles to translate, skipping")
            return content

        items_json = json.dumps(items_to_translate, ensure_ascii=False, indent=2)
        prompt = render_prompt(prompt_template, items_json=items_json)

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

    def _extract_json(self, text: str) -> dict:
        text = _strip_json_fence(text)

        if text.startswith('{') and text.endswith('}'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            try:
                return self._repair_json(json_str)
            except json.JSONDecodeError:
                pass

        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                result = json.loads(array_match.group(0))
                if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
                    return {"items": result}
            except json.JSONDecodeError:
                pass

        self.logger.error(f"Failed to extract JSON from response (first 500 chars): {text[:500]}")
        raise ValueError("No valid JSON found in response")

    def _repair_json(self, json_str: str) -> dict:
        repaired = re.sub(r',\s*([}\]])', r'\1', json_str)

        # Only quote unquoted keys: match word+colon that appears after { or , (not inside strings)
        # This avoids corrupting colons inside string values like "text": "foo: bar"
        repaired = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', repaired)
        repaired = re.sub(r'""(\w+)"":', r'"\1":', repaired)
        repaired = re.sub(r'"""(\w+)""":', r'"\1":', repaired)

        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(json_str):
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = json_str[:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
        raise json.JSONDecodeError("Could not repair JSON", json_str, 0)

    REQUIRED_SEGMENT_TYPES = {"opening", "dashboard", "story_scan", "closing"}
    DEFAULT_DURATIONS = {
        "opening": 25, "deep_dive": 60, "medium_dive": 30, "quick_news": 50, "closing": 12,
        "dashboard": 10, "story_scan": 100, "quick_briefs": 40, "context": 30, "viewpoint_a": 40, "viewpoint_b": 40,
        "comment_deep": 35, "synthesis": 30,
    }
    DEFAULT_EMOTIONS = {
        "opening": "curious", "deep_dive": "analytical", "medium_dive": "engaged",
        "quick_news": "upbeat", "closing": "warm", "dashboard": "neutral", "story_scan": "upbeat",
        "quick_briefs": "upbeat", "context": "analytical", "viewpoint_a": "engaged", "viewpoint_b": "engaged",
        "comment_deep": "engaged", "synthesis": "analytical",
    }

    @staticmethod
    def _split_prompt(prompt: str) -> List[Dict[str, str]]:
        """Split prompt at <!-- SYSTEM_CUT --> into system + user messages for prompt caching."""
        marker = "<!-- SYSTEM_CUT -->"
        if marker in prompt:
            system_part, user_part = prompt.split(marker, 1)
            messages = []
            system_text = system_part.strip()
            if system_text:
                messages.append({"role": "system", "content": system_text})
            messages.append({"role": "user", "content": user_part.strip()})
            return messages
        return [{"role": "user", "content": prompt}]

    def _dict_to_script(self, d: dict) -> Script:
        segments = []
        seen_types = set()

        # Extract top-level rich data to inject into segment meta
        deep_dive_data = d.get("deep_dive", {})
        medium_items_data = d.get("medium_items", [])
        quick_items_data = d.get("quick_items", [])

        # Build lookup: story_index -> item data
        medium_by_story = {m.get("story_index"): m for m in medium_items_data if isinstance(m, dict)}
        quick_by_story = {q.get("story_index"): q for q in quick_items_data if isinstance(q, dict)}

        for seg_dict in d.get("segments", []):
            seg_type = seg_dict.get("segment_type", "")
            seen_types.add(seg_type)

            scene_elements = []
            for elem_dict in seg_dict.get("scene_elements", []):
                scene_elements.append(SceneElement(
                    element_type=elem_dict.get("element_type", ""),
                    start_time=float(elem_dict.get("start_time", 0.0)),
                    end_time=float(elem_dict.get("end_time", 0.0)),
                    props=elem_dict.get("props", {})
                ))

            cues = []
            for cue_dict in seg_dict.get("cues", []):
                cues.append(Cue(
                    text=cue_dict.get("text", ""),
                    start_time=float(cue_dict.get("start_time", 0.0)),
                    end_time=float(cue_dict.get("end_time", 0.0)),
                ))

            raw_duration = seg_dict.get("estimated_duration", 30.0)
            try:
                estimated_duration = float(raw_duration)
            except (TypeError, ValueError):
                estimated_duration = self.DEFAULT_DURATIONS.get(seg_type, 30.0)

            meta = seg_dict.get("meta", {})

            # Inject rich data into segment meta
            if seg_type == "deep_dive" and deep_dive_data:
                meta["deep_dive"] = deep_dive_data
            elif seg_type == "medium_dive":
                story_idx = self._get_story_index(scene_elements)
                if story_idx is not None and story_idx in medium_by_story:
                    meta["medium_item"] = medium_by_story[story_idx]
            elif seg_type == "quick_news":
                meta["quick_items"] = quick_items_data

            segments.append(ScriptSegment(
                segment_type=seg_type,
                audio_text=seg_dict.get("audio_text", ""),
                estimated_duration=estimated_duration,
                emotion=seg_dict.get("emotion", self.DEFAULT_EMOTIONS.get(seg_type, "neutral")),
                scene_elements=scene_elements,
                cues=cues,
                meta=meta
            ))

        required_types = self.REQUIRED_SEGMENT_TYPES
        missing = required_types - seen_types
        if missing:
            self.logger.info(f"  LLM missing segment types: {missing}, adding defaults")
            for seg_type in missing:
                segments.append(ScriptSegment(
                    segment_type=seg_type,
                    audio_text="",
                    estimated_duration=self.DEFAULT_DURATIONS.get(seg_type, 30.0),
                    emotion=self.DEFAULT_EMOTIONS.get(seg_type, "neutral"),
                    scene_elements=[],
                    cues=[],
                    meta={}
                ))

        return Script(
            title=d.get("title", ""),
            description=d.get("description", ""),
            tags=d.get("tags", []),
            segments=segments
        )

    @staticmethod
    def _get_story_index(scene_elements: list) -> int | None:
        for elem in scene_elements:
            if elem.props.get("story_index") is not None:
                return elem.props["story_index"]
        return None

    def _validate_script_indices(self, script_dict: dict, max_stories: int):
        """Clamp story_index / comment_index in R2 scene_elements to valid range."""
        for seg in script_dict.get("segments", []):
            for elem in seg.get("scene_elements", []):
                props = elem.get("props", {})
                _clamp_index_in_place(props, "story_index", max_stories, "R2: scene_element", self.logger)
                _floor_index_in_place(props, "comment_index")
                for p_key in ("perspective_a", "perspective_b"):
                    p = props.get(p_key, {})
                    if isinstance(p, dict):
                        _clamp_index_in_place(p, "story_index", max_stories, f"R2: scene_element.{p_key}", self.logger)
                        _floor_index_in_place(p, "comment_index")
                for entry in props.get("entries", []):
                    _clamp_index_in_place(entry, "story_index", max_stories, "R2: dashboard entry", self.logger)
                for vp in props.get("viewpoints", []):
                    _floor_index_in_place(vp, "comment_index")
