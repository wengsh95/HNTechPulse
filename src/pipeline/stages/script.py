"""Script, translation, and audio stages for the video pipeline."""

from typing import Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import is_artifact_fresh
from src.pipeline.agent_variants import promote_variant_script, write_variants_index
from src.pipeline.paths import pipeline_path
from src.pipeline.script.io import (
    apply_audio_manifest,
    audio_manifest_is_usable,
    load_audio_manifest,
    load_script_lock,
    save_audio_manifest,
    script_audio_input_hash,
    script_editorial_hash,
)


class ScriptStageMixin:
    """Generate the script, apply selected translations, and synthesize audio."""

    def _step_write_script(self, content: ContentPackage, date: str) -> Script:
        lock = load_script_lock(date)
        if not (self.refresh_script or self.refresh_variants):
            script_path = pipeline_path(date, "script.json")
            if lock:
                existing = self.script_writer.load_script(date)
                expected_hash = lock.get("script_hash")
                current_hash = script_editorial_hash(existing)
                if expected_hash and expected_hash != current_hash:
                    raise RuntimeError(
                        "script.json changed after the last editorial lock. "
                        "Continue from a downstream step, or pass --refresh-script "
                        "to intentionally regenerate the script."
                    )
            elif self.agent_mode and script_path.exists():
                raise RuntimeError(
                    "Existing script.json has no script_lock.json. "
                    "Continue from a downstream step, or pass --refresh-script "
                    "to intentionally regenerate the script."
                )
        self.logger.info("=" * 50)
        self.logger.info("Step: Write script — narration generation")
        self.logger.info(f"Date: {date}, Stories: {len(content.items)}")
        self.logger.info(f"Model: {self.config.get('llm', {}).get('model', 'unknown')}")
        num_story_scan = min(
            self.config.get("pipeline", {}).get("target_story_count", 10),
            len(content.items),
        )
        self.logger.info(
            f"Expected script LLM calls: story_scan={num_story_scan} "
            f"(translations/enrichment may add separate calls)"
        )
        self.logger.info("=" * 50)

        if self.dry_run:
            self.logger.info("Dry run: skipping script generation")
            from src.core.models import ScriptSegment

            return Script(
                title="Test",
                description="Test",
                tags=[],
                segments=[
                    ScriptSegment(
                        segment_type="opening",
                        audio_text="测试音频",
                        duration=10.0,
                    )
                ],
            )

        if self.agent_mode and self._variant_count() > 1:
            return self._step_write_script_variants(content, date)

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _variant_count(self) -> int:
        variant_cfg = self.config.get("agent", {}).get("variants", {})
        if not variant_cfg.get("enabled", False):
            return 1
        return max(1, int(variant_cfg.get("count", 1) or 1))

    def _step_write_script_variants(self, content: ContentPackage, date: str) -> Script:
        count = self._variant_count()
        self.logger.info(f"Agent variants enabled: generating {count} script variants")
        variants = self.script_writer.write_variants(content, count=count)
        decision = self.agent_decision.select_script_variant(content, variants, date)
        index_variants = [
            {
                "variant_id": variant["variant_id"],
                "label": variant["label"],
                "strategy": variant["strategy"],
                "story_indices": variant["story_indices"],
                "preview": variant["preview"],
            }
            for variant in variants
        ]
        write_variants_index(
            date,
            index_variants,
            selected_variant=decision.get("selected_variant"),
            status=decision.get("status", "generated"),
        )
        if decision.get("status") != "continue" or not decision.get("selected_variant"):
            raise RuntimeError(
                f"Agent could not select a script variant: {decision.get('blocked_reason')}"
            )
        script = promote_variant_script(date, str(decision["selected_variant"]))
        self.script_writer.save_script(script, date)
        return script

    def _apply_comment_translations(
        self,
        content: ContentPackage,
        script: Optional[Script],
        date: str,
        *,
        save_script: bool = True,
    ) -> tuple[ContentPackage, Optional[Script]]:
        self.logger.info("  Translating selected comments")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment translation")
            return content, script

        if script is None:
            self.logger.warning("Script not loaded; skipping comment translation")
            return content, script

        content, script = self.translation_manager.translate(content, script, date)
        if save_script:
            self.script_writer.save_script(script, date)
        return content, script

    def _step_synthesize_audio(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Synthesize audio — TTS")
        if script is None:
            self.logger.warning("Script not loaded; skipping audio synthesis")
            return script

        audio_manifest_path = pipeline_path(date, "audio_manifest.json")
        audio_inputs = {
            "audio_input_hash": script_audio_input_hash(script),
            "segment_count": len(script.segments),
        }

        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            return script

        if is_artifact_fresh(audio_manifest_path, audio_inputs):
            manifest = load_audio_manifest(date)
            if manifest is not None and audio_manifest_is_usable(
                manifest, expected_segment_count=len(script.segments)
            ):
                self.logger.info(
                    "  Audio manifest matches current script; skipping TTS"
                )
                return apply_audio_manifest(script, manifest)
            self.logger.info("  Audio manifest is incomplete; regenerating TTS")

        script = self.tts_processor.process_audio(script, date, content)
        save_audio_manifest(script, date, config=self.config)
        self.script_writer.save_script(script, date)
        return script
