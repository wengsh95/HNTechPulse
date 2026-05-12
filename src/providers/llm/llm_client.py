import json
import re
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

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


class LLMClient:
    """Core LLM API call, JSON retry/parse/repair, spinner, diagnostics."""

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

        fast_cfg = llm_cfg.get("fast", {})
        self.fast_model = fast_cfg.get("model", self.model)
        self.fast_max_tokens = fast_cfg.get("max_tokens", 4096)
        self.fast_temperature = fast_cfg.get("temperature", 0.3)

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

    def call_llm_with_json_retry(
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
                self.extract_json(response_text)
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

    def extract_json(self, text: str) -> dict:
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
    def split_prompt(prompt: str) -> List[Dict[str, str]]:
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

    # ── Diagnostics ────────────────────────────────────────────

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

    # ── Spinner ────────────────────────────────────────────────

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
