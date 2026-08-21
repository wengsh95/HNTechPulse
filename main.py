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
    create_image_generator,
)
from src.pipeline.orchestrator import Orchestrator  # noqa: E402
from src.providers.enricher.article_enricher import ArticleEnricher  # noqa: E402
from src.providers.renderer.remotion_renderer import RemotionRenderer  # noqa: E402
from src.workflow import VIDEO_PIPELINE_STEPS, VIDEO_WORKFLOW_STEPS, WorkflowMachine  # noqa: E402
from src.workflow.persistence import WorkflowCorruptError  # noqa: E402


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
        description="HN TechPulse: Generate a narrated tech video from Hacker News"
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
        help="Resume from the selected product's failed/current/next step",
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
        "--refresh-script",
        action="store_true",
        help="Explicitly regenerate a manually changed editorial script",
    )
    parser.add_argument(
        "--refresh-selection",
        action="store_true",
        help="Explicitly allow agent prefilter to replace the locked story selection",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-render (clear render cache)"
    )
    parser.add_argument(
        "--steps",
        type=str,
        default=",".join(VIDEO_PIPELINE_STEPS),
        help=(
            "Steps to run (comma-separated: fetch, prefilter, fetch_comments, "
            "enrich_articles, judge_comments, write_script, draft_quick_news, "
            "prepare_story_images, title, cover_image, cover_thumbnail, "
            "draft_storyboard, human_review, apply_storyboard, prepare_subtitles, "
            "synthesize_audio, prepare_render, render, preview). Default runs "
            "the full managed video chain."
        ),
    )
    parser.add_argument(
        "--config", type=str, default="config/", help="Config directory or file path"
    )
    args = parser.parse_args()

    if (
        args.agent
        and not args.direct_agent_run
        and not os.environ.get("HN_AGENT_RUNNER")
    ):
        parser.error(
            "--agent runs must use the managed wrapper: "
            "uv run python scripts/agent_run.py --date YYYY-MM-DD. "
            "For manual debugging only, add --direct-agent-run."
        )

    config = load_config(args.config)
    if args.resume:
        workflow = WorkflowMachine(args.date, VIDEO_WORKFLOW_STEPS)
        if not workflow.path.exists():
            parser.error(
                f"--resume requested but no workflow state was found for {args.date}"
            )
        try:
            workflow.load()
        except (WorkflowCorruptError, OSError, ValueError) as exc:
            parser.error(f"--resume cannot read native workflow state: {exc}")
        report = workflow.status_report()
        metadata = report.get("metadata", {})
        requested_steps = [str(step) for step in metadata.get("requested_steps", [])]
        completed_steps = set(metadata.get("completed_pipeline_steps", []))
        resume_step = (
            metadata.get("failed_pipeline_step")
            or metadata.get("current_pipeline_step")
            or next(
                (step for step in requested_steps if step not in completed_steps),
                None,
            )
        )
        if not resume_step:
            parser.error(
                "--resume requested but the selected product state has no pending step"
            )
        if requested_steps and str(resume_step) in requested_steps:
            steps = requested_steps[requested_steps.index(str(resume_step)) :]
        else:
            steps = [str(resume_step)]
    else:
        steps = [s.strip() for s in args.steps.split(",")]

    product = "video"

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
    logger.info(f"Refresh selection: {args.refresh_selection}")
    logger.info(f"Pipeline steps: {steps}")
    logger.info("=" * 60)

    try:
        content_fetcher = create_fetcher("hn", config, debug=args.debug)

        llm_provider_name = config.get("llm", {}).get("provider", "openai")
        llm_provider = create_llm_provider(llm_provider_name, config, debug=args.debug)

        tts_provider_name = config.get("tts", {}).get("provider", "edge-tts")
        tts_provider = create_tts_provider(tts_provider_name, config, debug=args.debug)

        renderer = RemotionRenderer(config, debug=args.debug)
        logger.info("Using renderer: remotion")

        article_enricher = None
        enrich_config = config.get("enrich", {})
        if enrich_config.get("enabled", False):
            article_enricher = ArticleEnricher(
                llm_provider, config, debug=args.debug, agent_mode=args.agent
            )
            logger.info("Article enrichment enabled")

        image_generator = None
        img_cfg = config.get("image_generator", {})
        if img_cfg.get("enabled", False) and "cover_image" in steps:
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
            refresh_selection=args.refresh_selection,
            refresh_script=args.refresh_script,
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
