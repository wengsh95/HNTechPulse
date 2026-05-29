"""Pipeline progress tracking: execution summary, step timer, cache status."""

import json
import time
from contextlib import contextmanager
from pathlib import Path

from src.utils.logger import setup_logger


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
        date = self.date
        base = Path(f"data/{date}")
        entries: list[tuple[str, str, str]] = []

        content_path = base / "content.json"
        if content_path.exists():
            try:
                data = json.loads(content_path.read_text(encoding="utf-8"))
                n = len(data.get("items", []))
                entries.append(("fetch", "✓", f"{n} items cached"))
            except (json.JSONDecodeError, OSError):
                entries.append(("fetch", "✓", "cached"))
        else:
            entries.append(("fetch", "-", "will fetch"))

        prefilter_path = base / "prefilter.json"
        if prefilter_path.exists():
            try:
                data = json.loads(prefilter_path.read_text(encoding="utf-8"))
                stats = data.get("stats", {})
                entries.append(
                    (
                        "enrich",
                        "✓",
                        f"prefilter: {stats.get('kept', '?')}/{stats.get('total', '?')} kept",
                    )
                )
            except (json.JSONDecodeError, OSError):
                entries.append(("enrich", "✓", "prefilter cached"))
        else:
            entries.append(("enrich", "-", "will run prefilter"))

        for step, filename, label in [
            ("script", "comment_analysis.json", "comment analysis"),
            ("script", "comment_judgement.json", "comment judgement"),
            ("script", "script.json", "script"),
            ("produce", "translations.json", "translations"),
        ]:
            path = base / filename
            if path.exists():
                entries.append((step, "✓", f"{label} cached"))
            else:
                entries.append((step, "-", f"will generate {label}"))

        audio_dir = base / "audio"
        if audio_dir.exists() and any(audio_dir.iterdir()):
            entries.append(("produce", "✓", "audio cached"))
        else:
            entries.append(("produce", "-", "will synthesize"))

        return entries

    def _build_summary(self, force: bool) -> list[str]:
        config = self.config
        model = config.get("llm", {}).get("model", "unknown")
        fast_model = config.get("llm", {}).get("fast_model", "same")
        target = config.get("pipeline", {}).get("target_story_count", 10)
        focus = config.get("pipeline", {}).get("focus_items", 3)
        standard = config.get("pipeline", {}).get("standard_items", 3)
        quick = config.get("pipeline", {}).get("quick_items", 4)

        lines = [
            "=" * 60,
            "Pipeline Execution Summary",
            "=" * 60,
            f"  Date:   {self.date}",
            f"  Model:  {model} (fast: {fast_model})",
            f"  Steps:  {' → '.join(self.steps)}",
            f"  Target: {target} stories ({focus} focus / {standard} standard / {quick} quick)",
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
