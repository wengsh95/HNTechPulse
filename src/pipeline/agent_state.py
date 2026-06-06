"""Machine-readable pipeline state for agent-driven runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.pipeline.agent_io import append_agent_event, utc_now
from src.utils.atomic_io import atomic_write_json

BLOCK_MANUAL_DOWNLOAD = "manual_download_required"
BLOCK_MISSING_CREDENTIALS = "missing_credentials"
BLOCK_EXTERNAL_TOOL_MISSING = "external_tool_missing"
BLOCK_INSUFFICIENT_CONTEXT = "insufficient_story_context"


class AgentState:
    """Persist a compact run state that agents can inspect and resume from."""

    def __init__(self, date: str, steps: list[str], config: dict[str, Any]):
        self.date = date
        self.steps = list(steps)
        self.config = config
        self.path = Path(f"data/{date}/pipeline_state.json")
        self.task_path = Path(f"data/{date}/agent_tasks.json")
        self.completed_steps: list[str] = []
        self.current_step: str | None = None
        self.failed_step: str | None = None
        self.status = "running"
        self.blocked_reason: str | None = None
        self.degraded_items: list[dict[str, Any]] = []
        self.missing_manual_files: list[dict[str, Any]] = []
        self.blocked_items: list[dict[str, Any]] = []
        self.last_error: dict[str, str] | None = None

    def start_run(self) -> None:
        self.status = "running"
        self._write()
        append_agent_event(self.date, "run_started", steps=self.steps)

    def start_step(self, step: str) -> None:
        self.current_step = step
        self.failed_step = None
        self.last_error = None
        self._write()
        append_agent_event(self.date, "step_started", step=step)

    def complete_step(self, step: str) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if self.current_step == step:
            self.current_step = None
        self._write()
        append_agent_event(self.date, "step_completed", step=step)

    def fail_step(self, step: str, error: BaseException) -> None:
        self.status = "failed"
        self.current_step = None
        self.failed_step = step
        self.last_error = {
            "type": type(error).__name__,
            "message": str(error),
        }
        self._write()
        append_agent_event(
            self.date,
            "step_failed",
            step=step,
            error_type=type(error).__name__,
            message=str(error),
        )

    def add_degraded_items(self, step: str, items: list[Any], reason: str) -> None:
        for item in items:
            source_id = getattr(item, "source_id", None)
            title = getattr(item, "title", "") or ""
            url = getattr(item, "url", "") or ""
            item_reason = getattr(item, "enrichment_source", None) or reason
            self.degraded_items.append(
                {
                    "step": step,
                    "story_id": str(source_id) if source_id is not None else None,
                    "title": title,
                    "url": url,
                    "reason": item_reason,
                    "continued": True,
                }
            )
        if self.status == "running":
            self.status = "degraded"
        self._write()
        append_agent_event(
            self.date,
            "degraded_items_recorded",
            step=step,
            count=len(items),
            reason=reason,
        )

    def block_for_manual_files(self, step: str, items: list[Any]) -> None:
        self.missing_manual_files = [
            {
                "story_id": str(getattr(item, "source_id", "")),
                "title": getattr(item, "title", "") or "",
                "url": getattr(item, "url", "") or "",
                "expected_html": (
                    f"data/{self.date}/downloaded_pages/"
                    f"{getattr(item, 'source_id', '')}.html"
                ),
                "expected_pdf": (
                    f"data/{self.date}/downloaded_pages/"
                    f"{getattr(item, 'source_id', '')}.pdf"
                ),
            }
            for item in items
        ]
        self.block(
            step,
            BLOCK_MANUAL_DOWNLOAD,
            items=self.missing_manual_files,
            write_tasks=True,
        )

    def block(
        self,
        step: str,
        reason: str,
        *,
        items: list[dict[str, Any]] | None = None,
        write_tasks: bool = False,
    ) -> None:
        self.status = "blocked"
        self.current_step = None
        self.failed_step = step
        self.blocked_reason = reason
        self.blocked_items = items or []
        if write_tasks:
            self._write_task_list()
        self._write()
        append_agent_event(
            self.date,
            "run_blocked",
            step=step,
            reason=reason,
            task_file=(
                str(self.task_path).replace("\\", "/")
                if self.task_path.exists()
                else None
            ),
            item_count=len(self.blocked_items),
        )

    def finish_run(self) -> None:
        if self.status == "running":
            self.status = "complete"
        self.current_step = None
        self.failed_step = None
        self._write()
        append_agent_event(self.date, "run_finished", status=self.status)

    def _next_step(self) -> str | None:
        completed = set(self.completed_steps)
        for step in self.steps:
            if step not in completed:
                return step
        return None

    def _next_command(self) -> str | None:
        if self.status == "complete":
            return None
        if self.status == "blocked" and self.blocked_reason == BLOCK_MANUAL_DOWNLOAD:
            return (
                "Fetch the missing article pages with browser/MCP, save them to "
                f"data/{self.date}/downloaded_pages/, then run: "
                f"uv run python main.py --date {self.date} --resume --agent"
            )
        if (
            self.status == "blocked"
            and self.blocked_reason == BLOCK_INSUFFICIENT_CONTEXT
        ):
            return (
                "Gather more source context for the blocked stories, then run: "
                f"uv run python main.py --date {self.date} --resume --agent"
            )
        if self.status == "blocked" and self.blocked_reason in {
            BLOCK_MISSING_CREDENTIALS,
            BLOCK_EXTERNAL_TOOL_MISSING,
        }:
            return "Resolve the blocked environment issue, then rerun the command."
        next_step = self.failed_step or self.current_step or self._next_step()
        if next_step:
            return (
                f"uv run python main.py --date {self.date} --steps {next_step} --agent"
            )
        return None

    def _write_task_list(self) -> None:
        tasks = []
        resume_command = f"uv run python main.py --date {self.date} --resume --agent"
        for item in self.missing_manual_files:
            tasks.append(
                {
                    "schema_version": 2,
                    "task_type": "fetch_article",
                    "status": "pending",
                    "story_id": item["story_id"],
                    "title": item["title"],
                    "url": item["url"],
                    "save_as": {
                        "html": item["expected_html"],
                        "pdf": item["expected_pdf"],
                    },
                    "acceptable_outputs": ["html", "pdf"],
                    "minimum_success_condition": (
                        "Saved source file contains enough article text, official "
                        "project context, or reliable primary-source material for "
                        "factual script generation."
                    ),
                    "agent_capabilities": ["browser", "mcp"],
                    "repair_steps": [
                        "Open the URL with browser/MCP.",
                        "Prefer saving the rendered article HTML to save_as.html.",
                        "If the source is a PDF, save it to save_as.pdf.",
                        "If the original URL is blocked, look for an official mirror, repository, documentation page, or announcement.",
                        f"Resume with: {resume_command}",
                    ],
                    "failure_policy": (
                        "Do not fabricate article context. If no reliable source can "
                        "be found, leave the task pending and report the blocker."
                    ),
                    "resume_command": resume_command,
                }
            )
        atomic_write_json(
            self.task_path,
            {
                "schema_version": 2,
                "date": self.date,
                "created_at": utc_now(),
                "blocked_reason": self.blocked_reason,
                "repair_contract": {
                    "owner": "agent",
                    "allowed_tools": ["browser", "mcp"],
                    "acceptable_outputs": ["html", "pdf"],
                    "minimum_success_condition": (
                        "Every pending task has either save_as.html or save_as.pdf "
                        "created with reliable source context."
                    ),
                    "resume_command": resume_command,
                    "do_not_continue_without_source_context": True,
                },
                "tasks": tasks,
            },
        )

    def _artifacts(self) -> dict[str, str | None]:
        base = Path(f"data/{self.date}")
        artifacts = {
            "content": base / "content.json",
            "script": base / "script.json",
            "audio_dir": base / "audio",
            "title": base / "title.json",
            "cover": base / "cover.png",
            "publish_guide": base / "publish_guide.md",
            "render_props": Path("src/providers/renderer/remotion/public/props.json"),
            "output": base / "output.mp4",
        }
        return {
            name: str(path).replace("\\", "/") if path.exists() else None
            for name, path in artifacts.items()
        }

    def _write(self) -> None:
        payload = {
            "schema_version": 1,
            "updated_at": utc_now(),
            "date": self.date,
            "status": self.status,
            "steps": self.steps,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "blocked_reason": self.blocked_reason,
            "blocked_items": self.blocked_items,
            "missing_manual_files": self.missing_manual_files,
            "agent_task_file": (
                str(self.task_path).replace("\\", "/")
                if self.task_path.exists()
                else None
            ),
            "degraded_items": self.degraded_items,
            "last_error": self.last_error,
            "next_recommended_command": self._next_command(),
            "artifacts": self._artifacts(),
            "config": {
                "model": self.config.get("llm", {}).get("model"),
                "fast_model": self.config.get("llm", {})
                .get("fast", {})
                .get(
                    "model",
                    self.config.get("llm", {}).get("fast_model"),
                ),
                "target_story_count": self.config.get("pipeline", {}).get(
                    "target_story_count"
                ),
            },
        }
        atomic_write_json(self.path, payload)
