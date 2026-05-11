import json
import re
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading
from contextlib import contextmanager

from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from src.core.models import Script, ScriptSegment, SceneElement, ContentPackage, ContentItem, SelectionResult
from src.core.interfaces import LLMProvider
from src.core.prompts import render_prompt
from src.pipeline.comment_selection import clean_comment_text, compute_comment_quality, is_resource_pointer_comment
from src.pipeline.comment_judgement import normalize_story_judgement
from src.utils.logger import setup_logger
from src.utils.config import get_env


_JSON_FENCE_START_RE = re.compile(r'^```(?:json)?\s*\n?')
_JSON_FENCE_END_RE = re.compile(r'\n?```\s*$')


def _strip_json_fence(text: str) -> str:
    """Remove leading/trailing markdown code fences around JSON payloads."""
    text = text.strip()
    text = _JSON_FENCE_START_RE.sub('', text)
    text = _JSON_FENCE_END_RE.sub('', text)
    return text.strip()


def _clamp_index_in_place(d: dict, key: str, max_val: int, label: str, logger=None) -> None:
    """If d[key] is an int outside [0, max_val), clamp it in place and warn."""
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
        self.max_completion_tokens_cap = llm_cfg.get("max_completion_tokens_cap", 32768)
        self.cache_schema_version = llm_cfg.get("cache_schema_version", 2)

        fast_cfg = llm_cfg.get("fast", {})
        self.fast_model = fast_cfg.get("model", self.model)
        self.fast_max_tokens = fast_cfg.get("max_tokens", 4096)
        self.fast_temperature = fast_cfg.get("temperature", 0.3)

        self._total_stories = 0

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        retry=retry_if_exception_type((
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
            httpx.TimeoutException,
            httpx.TransportError,
        )),
        reraise=True,
    )
    def _create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        return self.client.chat.completions.create(**kwargs)

    def _call_llm_with_json_retry(
        self,
        messages: List[Dict[str, str]],
        label: str,
        max_tokens: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> str:
        current_messages = list(messages)
        effective_max_tokens = max_tokens or self.max_tokens
        effective_model = model or self.model
        effective_temperature = temperature if temperature is not None else self.temperature

        for attempt in range(1, self.json_parse_max_retries + 1):
            t0 = time.monotonic()

            with self._spinner(f"[{label}] API response pending (attempt {attempt})..."):
                response = self._create_chat_completion(
                    messages=current_messages,
                    model=effective_model,
                    max_tokens=effective_max_tokens,
                    temperature=effective_temperature,
                    extra_body=extra_body,
                )
            elapsed = time.monotonic() - t0

            if response is None or not getattr(response, "choices", None):
                self.logger.info(
                    f"  [{label}] API returned no choices (attempt {attempt}), retrying..."
                )
                continue

            choice = response.choices[0]
            message = choice.message
            response_text = (message.content or "") if message else ""
            finish_reason = choice.finish_reason
            usage = response.usage
            self._log_empty_or_truncated_diagnostics(
                label=label,
                attempt=attempt,
                response=response,
                choice=choice,
                message=message,
                response_text=response_text,
                finish_reason=finish_reason,
                max_tokens=effective_max_tokens,
            )

            if usage is None:
                self.logger.info(
                    f"  [{label}] Done in {elapsed:.1f}s (usage unavailable, attempt={attempt})"
                )
            else:
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
                self._log_truncated_response(label, attempt, response_text)
                if not response_text.strip():
                    self.logger.info(
                        f"  [{label}] Empty response with finish_reason=length. "
                        f"This usually means the compatible API/model consumed the token budget "
                        f"without producing visible content."
                    )
                    if label.startswith("comment_judge_"):
                        raise ValueError(
                            f"[{label}] Empty truncated response from comment judge"
                        )
                    self.logger.info(
                        f"  [{label}] Retrying without increasing max_tokens..."
                    )
                    current_messages = list(messages) + [
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was empty/truncated. "
                                "Return only a compact JSON object, no markdown or explanation."
                            ),
                        }
                    ]
                    continue
                if label.startswith("comment_judge_"):
                    raise ValueError(
                        f"[{label}] Truncated comment judge response"
                    )
                if effective_max_tokens >= self.max_completion_tokens_cap:
                    raise ValueError(
                        f"[{label}] Response truncated at max token cap "
                        f"({self.max_completion_tokens_cap})"
                    )
                self.logger.info(
                    f"  [{label}] Response truncated (finish_reason=length, "
                    f"max_tokens={effective_max_tokens}). "
                    f"Doubling max_tokens and retrying..."
                )
                effective_max_tokens = min(
                    effective_max_tokens * 2,
                    self.max_completion_tokens_cap,
                )
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

    def _log_empty_or_truncated_diagnostics(
        self,
        *,
        label: str,
        attempt: int,
        response,
        choice,
        message,
        response_text: str,
        finish_reason: str,
        max_tokens: int,
    ) -> None:
        """Persist full-ish response diagnostics when visible content is suspicious."""
        if finish_reason != "length" and response_text:
            return
        try:
            debug_dir = Path("data/llm_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)[:80]
            path = debug_dir / f"{safe_label}_attempt{attempt}_diagnostics.json"

            message_dump = None
            choice_dump = None
            response_dump = None
            if hasattr(message, "model_dump"):
                message_dump = message.model_dump()
            elif message is not None:
                message_dump = dict(getattr(message, "__dict__", {}))

            if hasattr(choice, "model_dump"):
                choice_dump = choice.model_dump()
            elif choice is not None:
                choice_dump = dict(getattr(choice, "__dict__", {}))

            if hasattr(response, "model_dump"):
                response_dump = response.model_dump()
            elif response is not None:
                response_dump = dict(getattr(response, "__dict__", {}))

            diagnostics = {
                "label": label,
                "attempt": attempt,
                "finish_reason": finish_reason,
                "max_tokens": max_tokens,
                "visible_content_length": len(response_text or ""),
                "message_attrs": sorted(
                    k for k in dir(message)
                    if not k.startswith("_")
                ) if message is not None else [],
                "message_dump": message_dump,
                "choice_dump": choice_dump,
                "response_dump": response_dump,
            }
            path.write_text(
                json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            self.logger.info(
                f"  [{label}] Saved suspicious response diagnostics to {path}"
            )

            reasoning = ""
            if message is not None:
                reasoning = (
                    getattr(message, "reasoning_content", None)
                    or getattr(message, "reasoning", None)
                    or ""
                )
            if reasoning:
                self.logger.info(
                    f"  [{label}] Response has non-empty reasoning field "
                    f"(chars={len(str(reasoning))}) while visible content chars="
                    f"{len(response_text or '')}"
                )
        except Exception as e:
            self.logger.info(f"  [{label}] Failed to save response diagnostics: {e}")

    def _log_truncated_response(self, label: str, attempt: int, response_text: str) -> None:
        """Log and persist truncated LLM output so prompt/schema issues are visible."""
        preview = (response_text or "")[:4000]
        self.logger.info(
            f"  [{label}] Truncated raw response preview "
            f"(attempt={attempt}, chars={len(response_text or '')}):\n{preview}"
        )
        try:
            debug_dir = Path("data/llm_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)[:80]
            path = debug_dir / f"{safe_label}_attempt{attempt}_truncated.json.txt"
            path.write_text(response_text or "", encoding="utf-8")
            self.logger.info(f"  [{label}] Saved truncated raw response to {path}")
        except Exception as e:
            self.logger.info(f"  [{label}] Failed to save truncated raw response: {e}")

    def _get_segment_cache_path(self, date: str, segment_type: str, story_index: int) -> Path:
        cache_dir = Path(f"data/{date}/segments")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{segment_type}_{story_index}.json"

    def _load_cached_segment(
        self,
        date: str,
        segment_type: str,
        story_index: int,
        expected_cache_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScriptSegment]:
        cache_path = self._get_segment_cache_path(date, segment_type, story_index)
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                seg_dict = json.load(f)
            cache_meta = seg_dict.get("_cache")
            if expected_cache_meta is not None and cache_meta != expected_cache_meta:
                self.logger.info(
                    f"    [{segment_type}_{story_index}] Cached segment metadata changed; regenerating"
                )
                return None
            scene_elements = [
                SceneElement(
                    element_type=e["element_type"],
                    start_time=e.get("start_time", 0.0),
                    end_time=e.get("end_time", 0.0),
                    props=e["props"]
                )
                for e in seg_dict.get("scene_elements", [])
            ]
            segment = ScriptSegment(
                segment_type=seg_dict["segment_type"],
                audio_text=seg_dict["audio_text"],
                estimated_duration=seg_dict["estimated_duration"],
                emotion=seg_dict.get("emotion", "neutral"),
                scene_elements=scene_elements,
                meta=seg_dict.get("meta", {}),
            )
            if segment_type == "story_scan_item" and not self._has_productized_story_fields(segment):
                self.logger.info(
                    f"    [{segment_type}_{story_index}] Cached segment lacks Milestone 2 fields; regenerating"
                )
                return None
            return segment
        except Exception as e:
            self.logger.warning(f"    Failed to load cached segment: {e}")
            return None

    @staticmethod
    def _has_productized_story_fields(segment: ScriptSegment) -> bool:
        event_elem = next(
            (elem for elem in segment.scene_elements if elem.element_type == "event_card"),
            None,
        )
        props = event_elem.props if event_elem else {}
        required = ("editor_angle", "dek", "key_points")
        return all(props.get(key) or segment.meta.get(key) for key in required)

    def _save_segment_cache(
        self,
        date: str,
        segment_type: str,
        story_index: int,
        segment: ScriptSegment,
        cache_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        cache_path = self._get_segment_cache_path(date, segment_type, story_index)
        seg_dict = {
            "_cache": cache_meta or {},
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
            "meta": segment.meta
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(seg_dict, f, ensure_ascii=False, indent=2)

    def _build_segment_cache_meta(
        self,
        *,
        prompt: str,
        story_id: Any,
        model: str,
        temperature: float,
    ) -> Dict[str, Any]:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return {
            "schema_version": self.cache_schema_version,
            "model": model,
            "temperature": temperature,
            "story_id": str(story_id),
            "prompt_hash": prompt_hash,
        }

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
        item = content.items[story_index]
        story_json = self._single_story_to_json(item, story_index, comments_data=comments_data)

        prompt_path = Path(prompt_template_path)
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = prompt_template_path

        comments_json_str = "{}"
        if comments_data:
            comments_json_str = json.dumps(comments_data, ensure_ascii=False, indent=2)

        prompt = render_prompt(
            prompt_template,
            story_json=story_json,
            story_index=str(story_index),
            comments_json=comments_json_str,
            date=date
        )

        cache_meta = self._build_segment_cache_meta(
            prompt=prompt,
            story_id=item.source_id,
            model=self.model,
            temperature=self.temperature,
        )

        cached = self._load_cached_segment(
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
        # Top-level fields are no longer duplicated in LLM output;
        # they live only in event_card.props. No injection needed.
        meta = seg_dict.get("meta", {})
        # Pass through structured narration from LLM output
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

        self._save_segment_cache(date, segment_type, story_index, segment, cache_meta=cache_meta)
        self.logger.info(f"    [{segment_type}_{story_index}] Done")
        return segment

    def translate_titles(self, content: ContentPackage, prompt_template: str) -> ContentPackage:
        """Translate all story titles using the fast/cheap model."""
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
        """Translate only the specified comments using the fast/cheap model.

        Args:
            content: ContentPackage with stories and comments.
            comment_refs: If values are strings (flat dict {"comment_S_C": "text"}),
                          translate them directly. If values are lists (legacy format
                          {story_index: [comment_index, ...]}), look up full comment
                          content from content.items.

        Returns:
            dict mapping "comment_{story_idx}_{comment_idx}" -> translated text.
        """
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

    def judge_story_comments(
        self,
        item: ContentItem,
        story_index: int,
        prompt_template_path: str = "prompts/comment_judge.md",
    ) -> dict:
        """Use the fast model to rank quote-worthy comments for one story."""
        story_json = self._story_comments_for_judge(item, story_index)
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

    @contextmanager
    def _spinner(self, label: str):
        t0 = time.monotonic()
        stop_event = threading.Event()

        if threading.current_thread() is not threading.main_thread():
            thread_name = threading.current_thread().name

            def _log_elapsed():
                while not stop_event.wait(5.0):
                    elapsed_sec = int(time.monotonic() - t0)
                    self.logger.info(
                        f"  {label} elapsed {elapsed_sec}s "
                        f"(thread={thread_name})"
                    )

            reporter = threading.Thread(target=_log_elapsed, daemon=True)
            reporter.start()
            try:
                yield
            finally:
                stop_event.set()
                reporter.join(timeout=1.0)
            return

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

    def _single_story_to_json(self, item, index: int, comments_data: Optional[Dict] = None) -> str:
        analyze_cfg = self.config.get("analyze", {})

        max_comments = analyze_cfg.get(
            "max_comments_for_llm",
            self.config.get("pipeline", {}).get("max_comments_for_r1_analyze", 10),
        )
        min_quality = analyze_cfg.get("min_quality_score", 0.1)

        # Prefer persisted analysis, but never send the raw 80-comment fallback to
        # the LLM. If analysis was skipped or cache did not load, compute the same
        # lightweight heuristic score here and still keep only top-N comments.
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
        if comments_data:
            story_dict["comment_judgement"] = comments_data
        result = json.dumps(story_dict, ensure_ascii=False, indent=2)
        self.logger.debug(f"Story[{index}] serialized: {len(result)} chars ({story_dict['truncated_to']} comments)")
        return result

    def _story_comments_for_judge(self, item, index: int) -> str:
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

        # Quote unquoted keys after { or , — use negative lookbehind for " to
        # avoid re-quoting already-quoted keys, and negative lookahead for ": to
        # avoid corrupting colons inside string values like "text": "foo: bar"
        repaired = re.sub(r'(?<=[{,])\s*(?<!")(\w+)(?!":)\s*:', r' "\1":', repaired)
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
