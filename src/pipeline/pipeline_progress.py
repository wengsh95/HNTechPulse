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

        content_data: dict | None = None
        content_path = base / "content.json"
        if content_path.exists():
            try:
                content_data = json.loads(content_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # 1. fetch
        if content_data is not None:
            n = len(content_data.get("items", []))
            entries.append(("fetch", "✓", f"{n} items cached"))
        else:
            entries.append(("fetch", "-", "will fetch"))

        # 2-5. content-mutating steps (state read from content.json)
        if content_data is not None:
            items = content_data.get("items", [])

            if (base / "prefilter.json").exists():
                entries.append(("prefilter", "✓", "prefilter cached"))
            else:
                entries.append(("prefilter", "-", "will prefilter"))

            if items and all(i.get("comment_count", 0) > 0 for i in items):
                entries.append(("fetch_comments", "✓", "comments attached"))
            else:
                entries.append(("fetch_comments", "-", "will fetch comments"))

            pending_states = {None, "pending", "fetch_failed", "extraction_failed"}
            pending = [i for i in items if i.get("enrichment_source") in pending_states]
            if items and not pending:
                entries.append(("enrich_articles", "✓", "articles enriched"))
            else:
                entries.append(
                    (
                        "enrich_articles",
                        "-",
                        f"{len(pending)}/{len(items)} need enrichment",
                    )
                )

            if items and all(i.get("title_cn") for i in items):
                entries.append(("translate_titles", "✓", "titles translated"))
            else:
                entries.append(("translate_titles", "-", "will translate titles"))
        else:
            for step in (
                "prefilter",
                "fetch_comments",
                "enrich_articles",
                "translate_titles",
            ):
                entries.append((step, "-", "fetch first"))

        # 6-8. comment analysis + judge + script
        for step, filename, label in [
            ("analyze_comments", "comment_analysis.json", "comment analysis"),
            ("judge_comments", "comment_judgement.json", "comment judgement"),
            ("write_script", "script.json", "script"),
        ]:
            if (base / filename).exists():
                entries.append((step, "✓", f"{label} cached"))
            else:
                entries.append((step, "-", f"will generate {label}"))

        # 9. translate_comments
        if (base / "translations.json").exists():
            entries.append(("translate_comments", "✓", "translations cached"))
        else:
            entries.append(("translate_comments", "-", "will translate"))

        # 10. synthesize_audio
        audio_dir = base / "audio"
        if audio_dir.exists() and any(audio_dir.iterdir()):
            entries.append(("synthesize_audio", "✓", "audio cached"))
        else:
            entries.append(("synthesize_audio", "-", "will synthesize"))

        # 11. title
        if (base / "title.json").exists():
            entries.append(("title", "✓", "title cached"))
        else:
            entries.append(("title", "-", "will generate title"))

        # 12. cover_image
        if (base / "cover_bg.png").exists():
            entries.append(("cover_image", "✓", "cover image cached"))
        else:
            entries.append(("cover_image", "-", "will generate cover image"))

        # 13. cover_thumbnail
        if (base / "cover.png").exists():
            entries.append(("cover_thumbnail", "✓", "cover thumbnail cached"))
        else:
            entries.append(("cover_thumbnail", "-", "will render cover thumbnail"))

        # 14. publish_guide
        if (base / "publish_guide.md").exists():
            entries.append(("publish_guide", "✓", "publish guide cached"))
        else:
            entries.append(("publish_guide", "-", "will generate guide"))

        # 15. prepare_render
        props_file = base / "cli_props.json"
        if props_file.exists():
            entries.append(("prepare_render", "✓", "props.json cached"))
        else:
            entries.append(("prepare_render", "-", "will write props.json"))

        return entries

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
