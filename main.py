#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

from src.utils.config import load_config
from src.utils.logger import setup_logger, get_log_file_path
from src.providers.factory import (
    create_fetcher,
    create_llm_provider,
    create_tts_provider,
    create_renderer,
)
from src.pipeline.orchestrator import Orchestrator
from src.providers.enricher.article_enricher import ArticleEnricher


def get_default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{value}'. Expected YYYY-MM-DD"
        )


def main():
    parser = argparse.ArgumentParser(
        description="HN TechPulse: Generate tech video from Hacker News"
    )
    parser.add_argument(
        "--date",
        type=validate_date,
        default=get_default_date(),
        help="Date to process (YYYY-MM-DD)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no API calls)")
    parser.add_argument(
        "--force", action="store_true", help="Force re-render (clear render cache)"
    )
    parser.add_argument(
        "--steps",
        type=str,
        default="fetch,enrich,script,produce,preview",
        help="Steps to run (comma-separated: fetch,enrich,script,produce,render,preview,editor,sync_preview)",
    )
    parser.add_argument(
        "--config", type=str, default="config/", help="Config directory or file path"
    )
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split(",")]

    config = load_config(args.config)

    product = "daily_brief"

    log_file = get_log_file_path(args.date) if not args.dry_run else None
    log_level = config.get("logging", {}).get("level", "INFO")
    logger = setup_logger(
        "hn_techpulse", log_file=log_file, debug=args.debug, level=log_level
    )

    logger.info("=" * 60)
    logger.info("Starting HN TechPulse")
    logger.info(f"Date: {args.date}")
    logger.info(f"Product: {product}")
    logger.info(f"Debug mode: {args.debug}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Pipeline steps: {steps}")
    logger.info("=" * 60)

    try:
        content_fetcher = create_fetcher("hn", config, debug=args.debug)

        llm_provider_name = config.get("llm", {}).get("provider", "openai")
        llm_provider = create_llm_provider(llm_provider_name, config, debug=args.debug)

        tts_provider_name = config.get("tts", {}).get("provider", "edge-tts")
        tts_provider = create_tts_provider(tts_provider_name, config, debug=args.debug)

        renderer = create_renderer("remotion", config, debug=args.debug)

        logger.info("Using Remotion renderer")

        article_enricher = None
        enrich_config = config.get("enrich", {})
        if enrich_config.get("enabled", False):
            article_enricher = ArticleEnricher(config, debug=args.debug)
            logger.info("Article enrichment enabled")

        orchestrator = Orchestrator(
            config=config,
            content_fetcher=content_fetcher,
            llm_provider=llm_provider,
            tts_provider=tts_provider,
            renderer=renderer,
            article_enricher=article_enricher,
            debug=args.debug,
            dry_run=args.dry_run,
        )

        orchestrator.run(
            date=args.date,
            steps=steps,
            force=args.force,
        )

        logger.info("Pipeline completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
