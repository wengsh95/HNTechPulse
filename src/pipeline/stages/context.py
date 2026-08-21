"""Static type context shared by the orchestrator stage mixins.

The runtime owner of these attributes is :class:`src.pipeline.orchestrator.Orchestrator`.
Keeping the declarations here lets each stage mixin be checked independently
without coupling the stage modules back to the concrete orchestrator class.
"""

from __future__ import annotations

from typing import Any


class OrchestratorContext:
    """Attributes and cross-stage helpers supplied by the orchestrator."""

    config: dict[str, Any]
    logger: Any
    dry_run: bool
    agent_mode: bool
    allow_degraded_enrichment: bool
    refresh_variants: bool
    refresh_selection: bool
    refresh_script: bool

    content_fetcher: Any
    llm_provider: Any
    tts_provider: Any
    renderer: Any
    article_enricher: Any | None
    image_generator: Any | None

    content_preparer: Any
    script_writer: Any
    tts_processor: Any
    translation_manager: Any
    comment_analyzer: Any
    comment_refiner: Any
    comment_judge: Any
    agent_decision: Any
    prefilter: Any
    _timing: Any

    _progress: Any
    _workflow: Any
    _workflow_completed_steps: set[str]
    _workflow_expected_steps: dict[str, set[str]]

    # These helpers are implemented by another mixin in Orchestrator's MRO.
    # The broad signatures keep this context independent from stage-specific
    # model details while allowing mypy to check cross-stage calls.
    def _apply_comment_translations(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _build_focus_story_input(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _extract_highlight_entries(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _mirror_cover_bg(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _write_publish_guide(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
