#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
sys.stderr.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

from src.utils.config import load_config  # noqa: E402
from src.utils.logger import setup_logger, get_log_file_path  # noqa: E402
from src.providers.factory import (  # noqa: E402
    create_fetcher,
    create_llm_provider,
    create_tts_provider,
    create_renderer,
    create_image_generator,
)
from src.pipeline.orchestrator import Orchestrator  # noqa: E402
from src.pipeline.agent_io import load_pipeline_state  # noqa: E402
from src.providers.enricher.article_enricher import ArticleEnricher  # noqa: E402


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
        "--resume",
        action="store_true",
        help="Resume from pipeline_state.json failed/current/next step",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Enable agent-friendly state tracking and structured blocking",
    )
    parser.add_argument(
        "--direct-agent-run",
        action="store_true",
        help=(
            "Bypass the agent_run.py wrapper guard. Intended for manual "
            "debugging only; agents should use scripts/agent_run.py."
        ),
    )
    parser.add_argument(
        "--allow-degraded-enrichment",
        action="store_true",
        help="In agent mode, continue after article enrichment failures",
    )
    parser.add_argument(
        "--refresh-variants",
        action="store_true",
        help="Clear script and variant caches before agent script generation",
    )
    parser.add_argument(
        "--renderer",
        type=str,
        choices=["remotion", "hyperframes"],
        default=None,
        help="Video renderer provider (overrides config.renderer.provider). Default: config or remotion.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-render (clear render cache)"
    )
    parser.add_argument(
        "--steps",
        type=str,
        default=(
            "fetch,prefilter,fetch_comments,enrich_articles,translate_titles,"
            "analyze_comments,judge_comments,write_script,translate_comments,"
            "synthesize_audio,title,cover_image,cover_thumbnail,publish_guide,"
            "prepare_render,render"
        ),
        help=(
            "Steps to run (comma-separated: fetch, prefilter, fetch_comments, "
            "enrich_articles, translate_titles, analyze_comments, judge_comments, "
            "write_script, translate_comments, synthesize_audio, title, cover_image, "
            "cover_thumbnail, publish_guide, prepare_render, render, preview). "
            "Default runs the full 16-step chain through video render; preview is "
            "always opt-in."
        ),
    )
    parser.add_argument(
        "--config", type=str, default="config/", help="Config directory or file path"
    )
    args = parser.parse_args()

    if args.agent and not args.direct_agent_run and not os.environ.get("HN_AGENT_RUNNER"):
        parser.error(
            "--agent runs must use the managed wrapper: "
            "uv run python scripts/agent_run.py --date YYYY-MM-DD. "
            "For manual debugging only, add --direct-agent-run."
        )

    config = load_config(args.config)
    if args.resume:
        state = load_pipeline_state(args.date)
        if not state:
            parser.error(
                f"--resume requested but data/{args.date}/pipeline_state.json was not found"
            )
        resume_step = (
            state.get("failed_step")
            or state.get("current_step")
            or next(
                (
                    step
                    for step in state.get("steps", [])
                    if step not in set(state.get("completed_steps", []))
                ),
                None,
            )
        )
        if not resume_step:
            parser.error(
                "--resume requested but pipeline_state.json has no pending step"
            )
        state_steps = [str(step) for step in state.get("steps", []) if step]
        if state_steps and str(resume_step) in state_steps:
            steps = state_steps[state_steps.index(str(resume_step)) :]
        else:
            steps = [str(resume_step)]
    else:
        steps = [s.strip() for s in args.steps.split(",")]

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
    logger.info(f"Agent mode: {args.agent}")
    logger.info(f"Allow degraded enrichment: {args.allow_degraded_enrichment}")
    logger.info(f"Refresh variants: {args.refresh_variants}")
    logger.info(f"Pipeline steps: {steps}")
    logger.info("=" * 60)

    try:
        content_fetcher = create_fetcher("hn", config, debug=args.debug)

        llm_provider_name = config.get("llm", {}).get("provider", "openai")
        llm_provider = create_llm_provider(llm_provider_name, config, debug=args.debug)

        tts_provider_name = config.get("tts", {}).get("provider", "edge-tts")
        tts_provider = create_tts_provider(tts_provider_name, config, debug=args.debug)

        renderer_name = (
            args.renderer
            or config.get("renderer", {}).get("provider", "remotion")
        )
        renderer = create_renderer(renderer_name, config, debug=args.debug)
        logger.info(f"Using renderer: {renderer_name}")

        article_enricher = None
        enrich_config = config.get("enrich", {})
        if enrich_config.get("enabled", False):
            article_enricher = ArticleEnricher(llm_provider, config, debug=args.debug)
            logger.info("Article enrichment enabled")

        image_generator = None
        img_cfg = config.get("image_generator", {})
        if img_cfg.get("enabled", False):
            image_generator = create_image_generator(
                img_cfg.get("provider", "noop"),
                config,
                debug=args.debug,
            )
            logger.info(f"Image generator enabled: {img_cfg.get('provider', 'noop')}")

        orchestrator = Orchestrator(
            config=config,
            content_fetcher=content_fetcher,
            llm_provider=llm_provider,
            tts_provider=tts_provider,
            renderer=renderer,
            article_enricher=article_enricher,
            image_generator=image_generator,
            debug=args.debug,
            dry_run=args.dry_run,
            agent_mode=args.agent,
            allow_degraded_enrichment=args.allow_degraded_enrichment,
            refresh_variants=args.refresh_variants,
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
