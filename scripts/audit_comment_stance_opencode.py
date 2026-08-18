"""Run the comment-stance audit against OpenCode's free OpenAI-compatible model."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.prompts import render_prompt  # noqa: E402
from src.pipeline.comment.judge import CommentAnalyzer  # noqa: E402
from src.pipeline.comment.selection import (  # noqa: E402
    select_distribution_comments,
)
from src.pipeline.content_io import ContentPreparer  # noqa: E402
from src.pipeline.comment import normalize_story_judgement  # noqa: E402
from src.providers.llm.llm_client import LLMClient  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.config import load_config  # noqa: E402


ENDPOINT = "https://opencode.ai/zen/v1/chat/completions"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", required=True, help="content.json path")
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--model", default="big-pickle")
    parser.add_argument(
        "--output", default="data/models/comment_stance_audit_opencode.json"
    )
    return parser.parse_args()


def extract_json(response_text: str) -> dict:
    text = (response_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("OpenCode response JSON must be an object")
    return value


def call_opencode(prompt: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    payload["temperature"] = 0.0
    payload["max_tokens"] = 8192
    api_key = os.environ.get("OPENCODE_ZEN_API_KEY", "").strip()
    headers = ["-H", "Content-Type: application/json"]
    if api_key:
        headers.extend(["-H", f"Authorization: Bearer {api_key}"])
    try:
        completed = subprocess.run(
            [
                "curl.exe",
                "-sS",
                "--fail-with-body",
                "-X",
                "POST",
                ENDPOINT,
                *headers,
                "--data-binary",
                "@-",
            ],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            check=True,
            timeout=180,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenCode request failed: {detail}") from exc
    envelope = json.loads(completed.stdout.decode("utf-8"))
    content = envelope["choices"][0]["message"]["content"]
    return extract_json(content)


def main() -> None:
    args = parse_args()
    config = load_config()
    config.setdefault("logging", {})["level"] = "ERROR"
    config.setdefault("analyze", {})["embedding_enabled"] = False

    content = ContentPreparer(config).load_content_path(Path(args.content))
    item_index, item = next(
        (index, candidate)
        for index, candidate in enumerate(content.items)
        if str(candidate.source_id) == str(args.story_id)
    )
    analyzer = CommentAnalyzer(config)
    analyzer._analyze_item(item)
    all_eligible = select_distribution_comments(item, max_n=100000)
    sample = select_distribution_comments(item, max_n=max(1, args.sample))

    labels = []
    prompt_template = Path("prompts/comment_distribution.md").read_text(
        encoding="utf-8"
    )
    batch_size = max(1, args.batch_size)
    for batch_index, start in enumerate(range(0, len(sample), batch_size)):
        batch = sample[start : start + batch_size]
        story_json = LLMClient.story_comments_for_judge(
            item,
            item_index,
            config,
            logger=None,
            candidates=[],
            distribution_candidates=batch,
        )
        prompt = render_prompt(prompt_template, story_json=story_json)
        result = normalize_story_judgement(
            call_opencode(prompt, args.model),
            item,
            distribution_ids={str(comment.source_id) for comment in batch},
        )
        labels.extend(result.get("stance_labels", []) or [])
        print(
            json.dumps(
                {
                    "batch": batch_index,
                    "batch_size": len(batch),
                    "labels": len(result.get("stance_labels", []) or []),
                },
                ensure_ascii=False,
            )
        )

    labels_by_id = {
        str(label.get("comment_id")): label
        for label in labels
        if isinstance(label, dict) and label.get("comment_id") is not None
    }
    rows = []
    for comment in sample:
        comment_id = str(comment.source_id)
        label = labels_by_id.get(comment_id, {})
        rows.append(
            {
                "story_id": str(item.source_id),
                "story_title": item.title,
                "discussion_target": item.editor_angle
                or item.why_it_matters
                or item.title,
                "comment_id": comment_id,
                "comment_text": comment.content,
                "parent_text": comment.parent_text,
                "production_stance": label.get("stance"),
                "production_confidence": label.get("confidence"),
                "production_context_sufficient": label.get("context_sufficient"),
                "gold_stance": None,
                "gold_note": "",
            }
        )

    payload = {
        "schema_version": 1,
        "provider": "opencode",
        "model": args.model,
        "story_id": str(item.source_id),
        "story_title": item.title,
        "eligible_count": len(all_eligible),
        "sample_count": len(sample),
        "labeled_count": len(labels_by_id),
        "rows": rows,
    }
    atomic_write_json(Path(args.output), payload)
    print(
        json.dumps(
            {
                "output": args.output,
                "story_id": str(item.source_id),
                "eligible_count": len(all_eligible),
                "sample_count": len(sample),
                "labeled_count": len(labels_by_id),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
