"""Pipeline progress tracking: execution summary, step timer, cache status."""

import time
from contextlib import contextmanager

from src.utils.logger import setup_logger
from src.workflow import presence_for_step


class PipelineProgress:
    def __init__(self, steps: list[str], date: str, config: dict):
        self.steps = steps
        self.date = date
        self.config = config
        self._current = 0
        self._total = len(steps)
        self._step_start = 0.0
        self._run_start = 0.0
        self.logger = setup_logger(__name__)

    def start(self):
        self._run_start = time.monotonic()

    def print_execution_summary(self, force: bool = False):
        self.start()
        for line in self._build_summary(force):
            self.logger.info(line)

    def elapsed(self) -> float:
        return time.monotonic() - self._run_start

    @contextmanager
    def step(self, name: str):
        self._current += 1
        self._step_start = time.monotonic()
        self.logger.info(f"[{self._current}/{self._total}] {name}")
        try:
            yield
            elapsed = time.monotonic() - self._step_start
            self.logger.info(
                f"[{self._current}/{self._total}] {name} ✓ ({elapsed:.1f}s)"
            )
        except KeyboardInterrupt:
            self.logger.info(f"[{self._current}/{self._total}] {name} ✗ (interrupted)")
            raise
        except Exception:
            self.logger.info(f"[{self._current}/{self._total}] {name} ✗")
            raise

    def _check_cache(self) -> list[tuple[str, str, str]]:
        """Step-ready triples for the summary, from the shared presence table."""
        return [
            (presence.name, "✓" if presence.ready else "-", presence.detail)
            for presence in presence_for_step(self.date)
        ]

    def _build_summary(self, force: bool) -> list[str]:
        config = self.config
        model = config.get("llm", {}).get("model", "unknown")
        fast_model = config.get("llm", {}).get("fast_model", "same")
        target = config.get("pipeline", {}).get("target_story_count", 3)

        lines = [
            "=" * 60,
            "Pipeline Execution Summary",
            "=" * 60,
            f"  Date:   {self.date}",
            f"  Model:  {model} (fast: {fast_model})",
            f"  Steps:  {' → '.join(self.steps)}",
            f"  Target: {target} stories",
        ]

        if force and "render" in self.steps:
            lines.append("  Force:  render cache will be cleared")

        lines.append("")
        lines.append("Cache status:")

        cache_entries = self._check_cache()
        in_steps = {s for s in self.steps}
        for name, mark, msg in cache_entries:
            if name not in in_steps:
                continue
            indicator = "✓" if mark == "✓" else "-"
            lines.append(f"  {indicator} {name:12s} {msg}")

        lines.append("=" * 60)
        return lines
