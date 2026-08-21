"""Render and preview stages for the video pipeline.

The stage methods remain part of :class:`Orchestrator`'s public behaviour via
``ProductionStageMixin`` while keeping renderer-specific orchestration out of
the main content pipeline module.
"""

from pathlib import Path
from typing import Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import (
    file_sha256,
    is_artifact_fresh,
    write_artifact_manifest,
)
from src.pipeline.paths import (
    pipeline_audio_dir,
    publish_path,
    render_path,
    render_remotion_dir,
)
from src.pipeline.render_inputs import build_render_inputs
from src.pipeline.story_images import require_story_images
from src.pipeline.stages.context import OrchestratorContext


class ProductionStageMixin(OrchestratorContext):
    """Implement the renderer-facing stages of the video workflow."""

    def _step_prepare_render(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Prepare render — write props.json and copy assets")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare render")

        if self.dry_run:
            self.logger.info("Dry run: skipping prepare_render")
            return

        require_story_images(script, date)
        # The guide depends only on the final content/title metadata, not on
        # renderer props. Generate it at this final packaging boundary.
        self._write_publish_guide(content, script, date)

        props_path = render_path(date, "cli_props.json")
        render_inputs = build_render_inputs(
            script, content, date, type(self.renderer).__name__
        )
        if is_artifact_fresh(props_path, render_inputs):
            self.logger.info("  Render props match current inputs; skipping")
            return

        audio_dir = str(pipeline_audio_dir(date))
        try:
            props_path, _, _ = self.renderer.write_props(
                script, audio_dir, content, date=date
            )
        except Exception as e:
            self.logger.error(f"Renderer.write_props failed: {e}", exc_info=True)
            raise

        if not props_path or not props_path.exists() or props_path.stat().st_size <= 0:
            raise RuntimeError(
                "Renderer.write_props did not produce a valid props file"
            )

        write_artifact_manifest(
            props_path,
            step="prepare_render",
            date=date,
            inputs={
                **render_inputs,
                "audio_dir": audio_dir,
            },
            config=self.config,
        )

    def _step_render(
        self,
        script: Optional[Script],
        date: str,
        content: Optional[ContentPackage] = None,
        force: bool = False,
    ) -> None:
        self.logger.info("Step: Render video")
        if self.dry_run:
            self.logger.info("Dry run: skipping render")
            return

        if script is None:
            try:
                script = self.script_writer.load_script(date, with_audio=True)
            except FileNotFoundError:
                raise FileNotFoundError("Script not found; cannot render")

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for render, scene elements may be incomplete"
                )

        output_path = Path(publish_path(date, "output.mp4"))
        props_path = render_path(date, "cli_props.json")
        render_inputs = {
            **build_render_inputs(script, content, date, type(self.renderer).__name__),
            "props_hash": file_sha256(props_path),
        }
        if not force and is_artifact_fresh(output_path, render_inputs):
            self.logger.info("  Video output matches current inputs; skipping render")
            return

        if force:
            self._clear_render_cache(date)

        output_path_str = str(output_path)
        audio_dir = str(pipeline_audio_dir(date))
        self.renderer.render(script, audio_dir, output_path_str, content, date=date)
        rendered = output_path
        if not rendered.exists() or rendered.stat().st_size <= 0:
            raise RuntimeError(
                f"Renderer did not produce a valid output file: {output_path_str}"
            )
        write_artifact_manifest(
            rendered,
            step="render",
            date=date,
            inputs={
                **build_render_inputs(
                    script, content, date, type(self.renderer).__name__
                ),
                "props_hash": file_sha256(render_path(date, "cli_props.json")),
            },
            config=self.config,
        )

    def _step_preview(
        self,
        script: Optional[Script],
        date: str,
        content: Optional[ContentPackage] = None,
    ) -> None:
        self.logger.info("Step: Preview (Remotion Studio)")
        if self.dry_run:
            self.logger.info("Dry run: skipping preview")
            return

        if script is None:
            try:
                script = self.script_writer.load_script(date, with_audio=True)
            except FileNotFoundError:
                self.logger.error("Script not found; cannot preview")
                return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for preview, scene elements may be incomplete"
                )

        audio_dir = str(pipeline_audio_dir(date))
        self.logger.info("Opening Remotion Studio at http://localhost:3000")
        self.logger.info(
            "Check the preview, then press Ctrl+C to stop and proceed to render."
        )
        self.renderer.preview(script, audio_dir, content, date=date)

    def _clear_render_cache(self, date: str) -> None:
        # Renderer-specific caches (Remotion chunk dirs, etc.)
        try:
            for path in self.renderer.cache_paths(date):
                if path.exists():
                    import shutil

                    shutil.rmtree(path)
                    self.logger.info(f"Cleared renderer cache: {path}")
        except Exception as e:
            self.logger.warning(f"Failed to clear renderer cache_paths: {e}")

        # RemotionRenderer also writes chunk outputs under its own out/; covered
        # by cache_paths() above. Keep this fallback for any renderer that
        # doesn't opt in.
        remotion_dir = Path("src/providers/renderer/remotion")
        # Match the new per-date runtime layout: data/{month}/{date}/remotion/chunks.
        chunk_dir = render_remotion_dir(date) / "chunks"
        if chunk_dir.exists() and not any(
            str(p).startswith(str(remotion_dir))
            for p in self.renderer.cache_paths(date)
        ):
            import shutil

            shutil.rmtree(chunk_dir)
            self.logger.info(f"Cleared all chunk caches: {chunk_dir}")

        output_path = publish_path(date, "output.mp4")
        if output_path.exists():
            output_path.unlink()
