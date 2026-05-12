"""
Test script for prompts/story_script.md

Constructs a realistic HN story with comments, injects persona + story data
into the prompt, calls the LLM, and prints the parsed JSON result.

Usage:
    python test_single_story_prompt.py
    python test_single_story_prompt.py --dry-run   # Skip API call, print rendered prompt only
"""

import json
import sys
import io
import argparse
from pathlib import Path

# Fix Unicode output on Windows (GBK console can't print emoji/CN chars)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from src.providers.llm.openai import OpenAILLMProvider
from src.core.prompts import render_prompt, PH_PERSONA
from src.core.models import ContentPackage, ContentItem, ContentComment


def build_test_story() -> ContentItem:
    """Build a single realistic HN story with comments for testing the prompt."""
    comments = [
        ContentComment(
            author="te_chris",
            content="I've been using Rust for embedded systems for about 2 years now. "
                     "The learning curve is real, but once you get past the borrow checker, "
                     "the resulting code is remarkably reliable. We've had zero memory bugs "
                     "in production across 50+ deployed devices.",
            upvotes=124,
        ),
        ContentComment(
            author="pragmatist_dev",
            content="Honestly, I think the embedded Rust hype is a bit overblown. "
                     "For most IoT projects, C with MISRA rules and good static analysis "
                     "gets you 90% of the safety with a fraction of the complexity. "
                     "The tooling ecosystem for embedded C is decades ahead.",
            upvotes=87,
        ),
        ContentComment(
            author="embedded_fan",
            content="The real killer feature isn't memory safety — it's Cargo. "
                     "Dependency management in embedded C is still a nightmare in 2025. "
                     "With Rust, I just add a line to Cargo.toml and it works on my STM32 "
                     "without fiddling with Makefiles for 3 hours.",
            upvotes=156,
        ),
        ContentComment(
            author="c_veteran",
            content="I've shipped safety-critical firmware in C for 15 years. "
                     "The tooling argument is valid, but Rust's HAL crates are maturing "
                     "fast. I'd say we're at a tipping point. New projects should seriously "
                     "evaluate Rust unless you have a hard C dependency.",
            upvotes=203,
        ),
        ContentComment(
            author="security_researcher",
            content="From a security perspective, the data is compelling: Android's switch "
                     "to Rust has reduced memory safety vulnerabilities by ~70%. "
                     "Embedded systems are increasingly networked — the attack surface "
                     "argument alone makes Rust worth the learning investment.",
            upvotes=178,
        ),
        ContentComment(
            author="skeptic_dev",
            content="Show me a Rust RTOS that's as mature as FreeRTOS and I'll switch tomorrow. "
                     "Until then, this is all academic. Most embedded teams can't afford to "
                     "be early adopters on a kernel.",
            upvotes=95,
        ),
        ContentComment(
            author="rustacean42",
            content="I ported our company's BLE sensor firmware from C to Rust last quarter. "
                     "Binary size went up 4KB (from 128KB to 132KB), but the bug report rate "
                     "dropped by 80% in the first month. The CTO was skeptical, now he's "
                     "asking other teams to evaluate Rust too.",
            upvotes=143,
        ),
    ]

    return ContentItem(
        source="hackernews",
        source_id="42404240",
        title="Rust for Embedded Systems: A Practical Guide (2026 Edition)",
        url="https://embedded-rust-book.com/2026",
        summary="A comprehensive guide to using Rust in embedded systems, "
                "covering HAL crates, RTOS integration, and real-world case studies.",
        title_cn="嵌入式 Rust 实践指南（2026 版）",
        score=842,
        comment_count=312,
        published_at=1715155200,
        comments=comments,
    )


def render_full_prompt(item: ContentItem, date: str, prompt_path: str, persona_path: str) -> str:
    """Read prompt template, inject persona + story data, return full prompt."""
    template = Path(prompt_path).read_text(encoding="utf-8")
    persona = Path(persona_path).read_text(encoding="utf-8")

    story_dict = {
        "index": 0,
        "id": item.source_id,
        "title": item.title,
        "url": item.url,
        "score": item.score,
        "comment_count": item.comment_count,
        "total_comments_available": len(item.comments),
        "truncated_to": len(item.comments),
        "comments": [
            {"author": c.author, "text": c.content}
            for c in item.comments
        ],
    }
    if item.article_summary:
        story_dict["article_summary"] = item.article_summary

    story_json_str = json.dumps(story_dict, ensure_ascii=False, indent=2)

    prompt = render_prompt(
        template,
        persona=persona,
        story_json=story_json_str,
        story_index="0",
        date=date,
    )
    return prompt


def main():
    parser = argparse.ArgumentParser(description="Test story_script.md prompt")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print rendered prompt without calling LLM")
    args = parser.parse_args()

    item = build_test_story()
    prompt = render_full_prompt(
        item=item,
        date="2026-05-08",
        prompt_path="prompts/story_script.md",
        persona_path="prompts/persona.md",
    )

    if args.dry_run:
        sep = "=" * 60
        print(sep)
        print("Rendered prompt (first 3000 chars):")
        print(sep)
        print(prompt[:3000])
        if len(prompt) > 3000:
            print(f"\n... ({len(prompt) - 3000} more chars)")
        print(sep)
        # Also save full prompt to file for inspection
        out_path = Path("data/test_rendered_prompt.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(prompt, encoding="utf-8")
        print(f"Full prompt saved to {out_path}")
        return

    # Initialize LLM provider from config.yaml
    import yaml
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))

    provider = OpenAILLMProvider(config, debug=True)

    # Call LLM
    provider.logger.info("Testing single_story_scan prompt...")
    response_text = provider._call_llm_with_json_retry(
        messages=provider._split_prompt(prompt),
        label="test_single_story",
    )

    result = provider._extract_json(response_text)

    sep = "=" * 60
    print("\n" + sep)
    print("Parsed JSON output:")
    print(sep)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Quick validation
    errors = []
    if "scene_elements" not in result:
        errors.append("Missing 'scene_elements'")
    else:
        event_card = next(
            (e for e in result["scene_elements"] if e.get("element_type") == "event_card"),
            None,
        )
        if event_card is None:
            errors.append("Missing event_card in scene_elements")
        else:
            props = event_card.get("props", {})
            for key in ("editor_angle", "dek", "key_points", "why_it_matters", "keywords"):
                if key not in props:
                    errors.append(f"Missing '{key}' in event_card.props")
    if "card_narrations" not in result:
        errors.append("Missing 'card_narrations'")
    elif len(result["card_narrations"]) != 3:
        errors.append(f"Expected 3 card_narrations, got {len(result['card_narrations'])}")

    if errors:
        print("\n[WARN] Validation warnings:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\n[OK] All basic fields present.")

    # Print key fields for quick inspection
    event_card = next(
        (e for e in result.get("scene_elements", []) if e.get("element_type") == "event_card"),
        {},
    )
    ep = event_card.get("props", {})
    print(f"\neditor_angle: {ep.get('editor_angle', 'N/A')}")
    print(f"dek: {ep.get('dek', 'N/A')}")
    narrations = result.get("card_narrations", [])
    total_chars = sum(len(n.get("audio_text", "")) for n in narrations)
    print(f"card_narrations ({len(narrations)} cards, {total_chars} chars total)")
    print(f"estimated_duration: {result.get('estimated_duration', 'N/A')}s")
    print(f"emotion: {result.get('emotion', 'N/A')}")

    # Save result to file
    out_path = Path("data/test_story_scan_result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResult saved to {out_path}")


if __name__ == "__main__":
    main()
