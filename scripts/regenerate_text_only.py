#!/usr/bin/env python3
"""Regenerate text-only publish artifacts without touching audio or render output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import (
    create_fetcher,
    create_image_generator,
    create_llm_provider,
    create_renderer,
    create_tts_provider,
)
from src.pipeline.content_io import ContentPreparer
from src.pipeline.orchestrator import Orchestrator
from src.pipeline.script import ScriptWriter
from src.providers.enricher.article_enricher import ArticleEnricher
from src.utils.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate title.json and publish_guide.md from existing content/script."
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default="config/")
    parser.add_argument(
        "--refresh-title",
        action="store_true",
        help="Delete data/{date}/title.json before regenerating title metadata.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    content_preparer = ContentPreparer(config)

    llm_provider = create_llm_provider(
        config.get("llm", {}).get("provider", "openai"), config, debug=False
    )
    tts_provider = create_tts_provider(
        config.get("tts", {}).get("provider", "edge-tts"), config, debug=False
    )
    renderer = create_renderer(
        config.get("renderer", {}).get("provider", "remotion"), config, debug=False
    )
    image_generator = None
    img_cfg = config.get("image_generator", {})
    if img_cfg.get("enabled", False):
        image_generator = create_image_generator(
            img_cfg.get("provider", "noop"), config, debug=False
        )
    article_enricher = (
        ArticleEnricher(llm_provider, config, debug=False)
        if config.get("enrich", {}).get("enabled", False)
        else None
    )

    orchestrator = Orchestrator(
        config=config,
        content_fetcher=create_fetcher("hn", config, debug=False),
        llm_provider=llm_provider,
        tts_provider=tts_provider,
        renderer=renderer,
        article_enricher=article_enricher,
        image_generator=image_generator,
        debug=False,
        dry_run=False,
        agent_mode=False,
    )

    content = content_preparer.load_content(args.date)
    script_writer = ScriptWriter(config, llm_provider, content_preparer)
    script = script_writer.load_script(args.date)
    if args.refresh_title:
        title_path = ROOT / "data" / args.date / "title.json"
        if title_path.exists():
            title_path.unlink()
    orchestrator._timing.compute_timeline(script)
    script = orchestrator._step_title(content, script, args.date)
    orchestrator.script_writer.save_script(script, args.date)
    orchestrator._step_publish_guide(content, script, args.date)
    print(f"Regenerated text-only artifacts for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
