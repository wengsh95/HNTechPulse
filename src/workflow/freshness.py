"""Freshness judgement for the video pipeline.

One module answers "which artifact is stale, why, and how to repair it", so the
agent scripts stop each keeping a private copy of the stale-detection logic
and stop passing free-text reason strings across a process seam.

Each stale result carries a structured ``StaleCode`` alongside the human
readable ``reason`` (the exact string preserved from the legacy wire format).
Consumers dispatch on the code; the reason string is generated here and read
by humans only.

``check_freshness`` replaces the stale-detection body of
``agent_status._build_video_status``; ``recovery_tail`` replaces
``agent_run._stale_recovery_steps``; ``command_for`` replaces
``agent_status._video_stale_command``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.pipeline.agent_io import file_sha256, is_artifact_fresh, stable_hash
from src.pipeline.human_review import script_approval_is_current
from src.pipeline.paths import (
    agent_path,
    pipeline_audio_dir,
    pipeline_path,
    publish_path,
    render_path,
    render_remotion_dir,
)
from src.pipeline.script.io import (
    audio_manifest_is_usable,
    load_audio_manifest,
    load_script,
    script_audio_input_hash,
    script_editorial_hash,
)
from src.workflow.planner import downstream_tail
from src.workflow.reporting import load_workflow_report
from src.workflow.steps import PLANNED_STEPS


class StaleCode(str, Enum):
    """Structured staleness codes.

    Each member's ``value`` is the exact reason string emitted in the wire
    format (legacy-pinned); ``repair`` names the step that recovers from the
    staleness.  The codes fall into two families:

    - content/editorial staleness (content, storyboard, story images,
      approval, publish guide) — detected by hash/manifest mismatch plus the
      mtime quick gate.
    - downstream media staleness (subtitle plan, audio manifest, render
      props/output, public props mirror) — detected by manifest equality,
      the render-inputs fingerprint, or the mtime quick gate.
    """

    CONTENT_NEWER_THAN_SCRIPT = "content.json is newer than script.json"
    STORYBOARD_NEWER_THAN_SCRIPT = "storyboard.json is newer than script.json"
    STORY_IMAGES_MISSING = (
        "story_images.json is missing; every story needs a local image"
    )
    SCRIPT_APPROVAL_STALE = (
        "script_approval.json is missing or does not match script.json"
    )
    SCRIPT_NEWER_THAN_CLI_PROPS = "script.json is newer than cli_props.json"
    SUBTITLE_PLAN_MISSING = "subtitle_plan.json is missing"
    SUBTITLE_PLAN_STALE = "subtitle_plan.json does not match script.json"
    AUDIO_MANIFEST_STALE = "audio_manifest.json input hash does not match script.json"
    AUDIO_MANIFEST_UNUSABLE = "audio_manifest.json references missing audio files"
    AUDIO_MANIFEST_MISSING = "audio_manifest.json is missing"
    AUDIO_VALIDATION_ERROR = "cannot validate audio manifest against script.json"
    RENDER_OUTPUT_STALE = "cli_props.json is newer than output.mp4"
    PUBLIC_PROPS_MIRROR_MISSING = "public Remotion props mirror is missing"
    PUBLISH_GUIDE_STALE = "publish_guide.md input hash does not match content/script"

    @property
    def repair(self) -> str:
        """Recovery-tail entry point for this staleness."""
        return {
            StaleCode.CONTENT_NEWER_THAN_SCRIPT: "write_script",
            StaleCode.STORYBOARD_NEWER_THAN_SCRIPT: "apply_storyboard",
            StaleCode.STORY_IMAGES_MISSING: "prepare_story_images",
            StaleCode.SCRIPT_APPROVAL_STALE: "human_review",
            StaleCode.SCRIPT_NEWER_THAN_CLI_PROPS: "prepare_subtitles",
            StaleCode.SUBTITLE_PLAN_MISSING: "prepare_subtitles",
            StaleCode.SUBTITLE_PLAN_STALE: "prepare_subtitles",
            StaleCode.AUDIO_MANIFEST_STALE: "prepare_subtitles",
            StaleCode.AUDIO_MANIFEST_UNUSABLE: "prepare_subtitles",
            StaleCode.AUDIO_MANIFEST_MISSING: "prepare_subtitles",
            StaleCode.AUDIO_VALIDATION_ERROR: "prepare_subtitles",
            StaleCode.RENDER_OUTPUT_STALE: "prepare_subtitles",
            StaleCode.PUBLIC_PROPS_MIRROR_MISSING: "prepare_subtitles",
            StaleCode.PUBLISH_GUIDE_STALE: "prepare_render",
        }[self]


@dataclass(frozen=True)
class StaleArtifact:
    """One stale artifact with its human-readable and structured reasons."""

    artifact: str
    code: StaleCode

    @property
    def reason(self) -> str:
        return self.code.value

    def as_wire_dict(self) -> dict[str, str]:
        """Wire-format record emitted in ``stale_artifacts``.

        The reason string is the legacy-pinned text; ``code`` is added for
        machine consumers so they can stop parsing the reason text.
        """
        return {
            "artifact": self.artifact,
            "reason": self.reason,
            "code": self.code.value,
        }


@dataclass(frozen=True)
class FreshnessReport:
    """Result of checking a date's artifacts for staleness."""

    stale: list[StaleArtifact] = field(default_factory=list)
    approval_current: bool = False


# ── Local helpers (moved verbatim from the agent scripts) ────────────────


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_newer(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and a.stat().st_mtime > b.stat().st_mtime


def publish_guide_context(
    date: str, content_path: Path, script_path: Path
) -> dict[str, Any] | None:
    """Input context whose hash keys the publish-guide manifest."""
    content_data = _read_json(content_path)
    script_data = _read_json(script_path)
    if not isinstance(content_data, dict) or not isinstance(script_data, dict):
        return None
    title_data = _read_json(publish_path(date, "title.json"))
    if not isinstance(title_data, dict):
        title_data = {}
    items_payload = []
    for item in content_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        items_payload.append(
            {
                "title_cn": item.get("title_cn") or item.get("title"),
                "title": item.get("title"),
                "editor_angle": item.get("editor_angle") or item.get("dek") or "",
                "category": item.get("category") or "",
                "keywords": item.get("keywords") or [],
                "score": item.get("score"),
                "comment_count": item.get("comment_count"),
            }
        )
    return {
        "script_title": title_data.get("title")
        or script_data.get("title")
        or "HN每日观察",
        "script_description": title_data.get("description")
        or script_data.get("description")
        or "",
        "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
        "prompt_hash": file_sha256(Path("prompts/publish_guide.md")),
        "date": date,
    }


def has_stale_publish_guide(
    date: str, content_path: Path, script_path: Path, guide_path: Path
) -> bool:
    if not guide_path.exists():
        return False
    context = publish_guide_context(date, content_path, script_path)
    if context is None:
        return False
    manifest = _read_json(guide_path.with_suffix(guide_path.suffix + ".manifest.json"))
    return not isinstance(manifest, dict) or manifest.get("input_hash") != stable_hash(
        context
    )


# ── Stale detection ──────────────────────────────────────────────────────


def check_freshness(date: str) -> FreshnessReport:
    """Return every stale artifact for a date, with reason + repair code.

    Replaces the stale-detection body of ``agent_status._build_video_status``.
    ``approval_current`` is returned alongside so the status renderer exposes
    it without recomputing script approval.
    """
    content = pipeline_path(date, "content.json")
    script = pipeline_path(date, "script.json")
    storyboard = pipeline_path(date, "storyboard.json")
    story_images = pipeline_path(date, "story_images.json")
    subtitle_plan = pipeline_path(date, "subtitle_plan.json")
    audio_manifest = pipeline_path(date, "audio_manifest.json")
    cli_props = render_path(date, "cli_props.json")
    public_props = render_remotion_dir(date) / "public" / "props.json"
    output = publish_path(date, "output.mp4")
    publish_guide = publish_path(date, "publish_guide.md")
    approval_path = agent_path(date, "script_approval.json")

    workflow_report = load_workflow_report(date)
    workflow_present = workflow_report is not None
    media_present = cli_props.exists() or output.exists()

    stale: list[StaleArtifact] = []

    def add(code: StaleCode, artifact: Path) -> None:
        stale.append(
            StaleArtifact(artifact=str(artifact).replace("\\", "/"), code=code)
        )

    # mtime quick gates (fast fail before the manifest checks below).
    if _is_newer(content, script):
        add(StaleCode.CONTENT_NEWER_THAN_SCRIPT, script)
    if _is_newer(storyboard, script):
        add(StaleCode.STORYBOARD_NEWER_THAN_SCRIPT, storyboard)

    if (
        script.exists()
        and not story_images.exists()
        and (workflow_present or media_present)
    ):
        add(StaleCode.STORY_IMAGES_MISSING, story_images)

    approval_current = False
    if script.exists():
        try:
            loaded_script = load_script(date)
            approval_current = script_approval_is_current(date, loaded_script)
            if not approval_current:
                add(StaleCode.SCRIPT_APPROVAL_STALE, approval_path)
            render_manifest = _read_json(
                cli_props.with_suffix(cli_props.suffix + ".manifest.json")
            )
            render_inputs = (
                render_manifest.get("inputs")
                if isinstance(render_manifest, dict)
                else None
            )
            if not isinstance(render_inputs, dict) or any(
                render_inputs.get(key) != expected
                for key, expected in {
                    "script_editorial_hash": script_editorial_hash(loaded_script),
                    "audio_manifest_hash": file_sha256(audio_manifest),
                    "content_hash": file_sha256(content),
                }.items()
            ):
                if _is_newer(script, cli_props) or not cli_props.exists():
                    add(StaleCode.SCRIPT_NEWER_THAN_CLI_PROPS, cli_props)
            subtitle_plan_data = _read_json(subtitle_plan)
            if not subtitle_plan.exists():
                if workflow_present or media_present:
                    add(StaleCode.SUBTITLE_PLAN_MISSING, subtitle_plan)
            elif not isinstance(subtitle_plan_data, dict) or subtitle_plan_data.get(
                "audio_input_hash_after"
            ) != script_audio_input_hash(loaded_script):
                add(StaleCode.SUBTITLE_PLAN_STALE, subtitle_plan)
            audio_inputs = {
                "audio_input_hash": script_audio_input_hash(loaded_script),
                "segment_count": len(loaded_script.segments),
            }
            if audio_manifest.exists():
                manifest = load_audio_manifest(date)
                if not is_artifact_fresh(audio_manifest, audio_inputs):
                    add(StaleCode.AUDIO_MANIFEST_STALE, audio_manifest)
                elif manifest is not None and not audio_manifest_is_usable(
                    manifest, expected_segment_count=len(loaded_script.segments)
                ):
                    add(StaleCode.AUDIO_MANIFEST_UNUSABLE, audio_manifest)
            elif pipeline_audio_dir(date).exists() or media_present:
                add(StaleCode.AUDIO_MANIFEST_MISSING, audio_manifest)
        except (OSError, ValueError, TypeError):
            add(StaleCode.AUDIO_VALIDATION_ERROR, audio_manifest)

    if _is_newer(cli_props, output):
        output_manifest = _read_json(
            output.with_suffix(output.suffix + ".manifest.json")
        )
        output_inputs = (
            output_manifest.get("inputs") if isinstance(output_manifest, dict) else None
        )
        output_matches_current = False
        if isinstance(output_inputs, dict) and script.exists():
            try:
                current_script = load_script(date)
                output_matches_current = not any(
                    output_inputs.get(key) != expected
                    for key, expected in {
                        "script_editorial_hash": script_editorial_hash(current_script),
                        "audio_manifest_hash": file_sha256(audio_manifest),
                        "content_hash": file_sha256(content),
                        "props_hash": file_sha256(cli_props),
                    }.items()
                )
            except (OSError, ValueError, TypeError):
                output_matches_current = False
        if not output_matches_current:
            add(StaleCode.RENDER_OUTPUT_STALE, output)
    if cli_props.exists() and not public_props.exists():
        add(StaleCode.PUBLIC_PROPS_MIRROR_MISSING, public_props)
    if has_stale_publish_guide(date, content, script, publish_guide):
        add(StaleCode.PUBLISH_GUIDE_STALE, publish_guide)

    return FreshnessReport(stale=stale, approval_current=approval_current)


# ── Recovery tail (replaces agent_run._stale_recovery_steps) ─────────────


def _record_codes(records: list[dict[str, Any]]) -> set[StaleCode]:
    """Resolve the stale codes present in wire records.

    Code-first (new records carry ``code``); falls back to resolving the
    legacy free-text ``reason`` so older status snapshots keep working.  This
    resolution is the single place reason text is turned back into a code.
    """
    codes: set[StaleCode] = set()
    for record in records:
        raw_code = record.get("code")
        if raw_code:
            try:
                codes.add(StaleCode(raw_code))
                continue
            except ValueError:
                pass
        reason = record.get("reason") or ""
        for member in StaleCode:
            if member.value == reason:
                codes.add(member)
                break
    return codes


def recovery_tail(stale_records: list[dict[str, Any]]) -> list[str] | None:
    """Recovery step list from stale records.

    Mirrors the legacy ``agent_run._stale_recovery_steps`` branch order and
    outputs (pinned by tests).  Codes drive the dispatch; "reason" strings
    from older snapshots fall back through the legacy matching operators, all
    in one place.
    """
    codes = _record_codes(stale_records)
    reasons = [record.get("reason") or "" for record in stale_records]

    def has(*members: StaleCode) -> bool:
        return any(code in codes for code in members)

    def any_reason(pred) -> bool:
        return any(pred(reason) for reason in reasons)

    if has(StaleCode.CONTENT_NEWER_THAN_SCRIPT) or any_reason(
        lambda r: r.startswith("content.json is newer")
    ):
        return list(PLANNED_STEPS)[PLANNED_STEPS.index("write_script") :]
    if has(StaleCode.SCRIPT_APPROVAL_STALE) or any_reason(
        lambda r: "script_approval.json" in r
    ):
        return list(PLANNED_STEPS)[PLANNED_STEPS.index("human_review") :]
    if has(StaleCode.STORYBOARD_NEWER_THAN_SCRIPT) or any_reason(
        lambda r: "storyboard.json is newer" in r
    ):
        return downstream_tail("apply_storyboard")
    if has(
        StaleCode.SUBTITLE_PLAN_MISSING, StaleCode.SUBTITLE_PLAN_STALE
    ) or any_reason(lambda r: "subtitle_plan.json" in r):
        return downstream_tail("prepare_subtitles")
    if has(
        StaleCode.AUDIO_MANIFEST_STALE,
        StaleCode.AUDIO_MANIFEST_UNUSABLE,
        StaleCode.AUDIO_MANIFEST_MISSING,
        StaleCode.AUDIO_VALIDATION_ERROR,
    ) or any_reason(lambda r: "audio_manifest.json" in r):
        return downstream_tail("prepare_subtitles")
    if has(StaleCode.PUBLISH_GUIDE_STALE) or any_reason(lambda r: "publish_guide" in r):
        return downstream_tail("prepare_render")
    if has(StaleCode.SCRIPT_NEWER_THAN_CLI_PROPS) or any_reason(
        lambda r: "script.json is newer than cli_props.json" in r
    ):
        return downstream_tail("prepare_subtitles")
    if has(
        StaleCode.RENDER_OUTPUT_STALE, StaleCode.PUBLIC_PROPS_MIRROR_MISSING
    ) or any_reason(
        lambda r: (
            "cli_props.json is newer than output.mp4" in r
            or "public Remotion props mirror is missing" in r
        )
    ):
        return downstream_tail("prepare_subtitles")
    return None


# ── Repair command (replaces agent_status._video_stale_command) ──────────


_LEGACY_COMMAND_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (artifact substrings, command template, why) in legacy priority order.
    (
        ("script.json",),
        "uv run python scripts/internal/agent/agent_run.py --date {date} --refresh-script",
        "Content changed after script generation; regenerate video artifacts.",
    ),
    (
        ("script_approval.json",),
        "uv run python scripts/internal/agent/agent_run.py --date {date} --from human_review",
        "The current editorial script has not passed the human checkpoint.",
    ),
    (
        ("storyboard.json",),
        "uv run python scripts/internal/agent/agent_run.py --date {date} --from apply_storyboard",
        "storyboard.json changed after script application; rebuild video visuals.",
    ),
    (
        ("subtitle_plan.json",),
        "uv run python scripts/internal/agent/agent_run.py --date {date} "
        "--steps prepare_subtitles,synthesize_audio,prepare_render,render",
        "The local subtitle plan is missing or does not match script.json.",
    ),
    (
        ("audio_manifest.json",),
        "uv run python scripts/internal/agent/agent_run.py --date {date} "
        "--steps prepare_subtitles,synthesize_audio,prepare_render,render",
        "The editorial script changed; regenerate audio and downstream video artifacts.",
    ),
)


def command_for(date: str, stale_records: list[dict[str, Any]]) -> dict[str, str]:
    """Recommended repair command for a set of stale records.

    Mirrors the legacy ``agent_status._video_stale_command`` branch order and
    exact command text (pinned by tests).  Codes drive the dispatch; legacy
    fixtures fall back to artifact-substring matching, all in one place.
    """
    codes = _record_codes(stale_records)
    artifacts = [item.get("artifact", "") for item in stale_records]

    def has(*members: StaleCode) -> bool:
        return any(code in codes for code in members)

    def any_fragment(fragments: tuple[str, ...]) -> bool:
        return any(
            fragment in artifact for artifact in artifacts for fragment in fragments
        )

    code_to_rule: tuple[tuple[set[StaleCode], int], ...] = (
        ({StaleCode.CONTENT_NEWER_THAN_SCRIPT}, 0),
        ({StaleCode.SCRIPT_APPROVAL_STALE}, 1),
        ({StaleCode.STORYBOARD_NEWER_THAN_SCRIPT}, 2),
        ({StaleCode.SUBTITLE_PLAN_MISSING, StaleCode.SUBTITLE_PLAN_STALE}, 3),
        (
            {
                StaleCode.AUDIO_MANIFEST_STALE,
                StaleCode.AUDIO_MANIFEST_UNUSABLE,
                StaleCode.AUDIO_MANIFEST_MISSING,
                StaleCode.AUDIO_VALIDATION_ERROR,
            },
            4,
        ),
    )
    for members, rule_idx in code_to_rule:
        if has(*members):
            fragments, template, why = _LEGACY_COMMAND_RULES[rule_idx]
            return {
                "command": template.format(date=date),
                "why": why,
            }
    for rule_idx, (fragments, template, why) in enumerate(_LEGACY_COMMAND_RULES):
        if any_fragment(fragments):
            return {
                "command": template.format(date=date),
                "why": why,
            }
    return {
        "command": (
            f"uv run python scripts/internal/agent/agent_run.py --date {date} "
            "--steps prepare_subtitles,prepare_render,render"
        ),
        "why": "Render props/output look stale or incomplete.",
    }
