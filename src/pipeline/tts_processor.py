import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.core.interfaces import TTSProvider, TTSResult
from src.core.models import Cue, Script, ScriptSegment
from src.pipeline.timing_engine import TimingEngine
from src.utils.audio import get_audio_duration
from src.utils.logger import setup_logger


class TTSProcessor:
    def __init__(self, tts_provider: TTSProvider, config: dict, debug: bool = False, level=None):
        self.tts_provider = tts_provider
        self.config = config
        timing_cfg = config.get("timing", {})
        self.subtitle_gap = float(timing_cfg.get("subtitle_gap", 0.0))
        self.timing_engine = TimingEngine(
            segment_gap=float(timing_cfg.get("segment_gap", 0.0)),
            story_gap=float(timing_cfg.get("story_gap", 0.0)),
            debug=debug, level=level,
        )
        self.logger = setup_logger(__name__, debug=debug, level=level)
        tts_config = config.get("tts", {})
        self.max_workers = tts_config.get("max_workers", 3)
        if self.max_workers < 1:
            self.max_workers = 1
        elif self.max_workers > 8:
            self.max_workers = 8

    def process_audio(self, script: Script, date: str, content=None) -> Script:
        """Synthesize audio for all segments in parallel, compute timings, validate."""
        audio_dir = Path(f"data/{date}/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        tasks = self._collect_tasks(script, audio_dir)
        self._execute_tasks(tasks)
        self._assemble_results(script, tasks, audio_dir)

        self.timing_engine.compute_timeline(script)
        self.timing_engine.set_scene_element_times(script)
        self.timing_engine.validate_segment_duration(script)
        return script

    # ── Phase 1: collect all synthesis tasks ──

    def _collect_tasks(self, script: Script, audio_dir: Path) -> list[dict]:
        tasks = []
        for seg_idx, segment in enumerate(script.segments):
            if segment.segment_type == "story_scan" and self._has_per_card_audio(segment):
                tasks.extend(self._collect_story_scan_tasks(segment, seg_idx, audio_dir))
            else:
                task = self._collect_segment_task(segment, seg_idx, audio_dir)
                if task is not None:
                    tasks.append(task)
        return tasks

    @staticmethod
    def _has_per_card_audio(segment: ScriptSegment) -> bool:
        return any(
            elem.props.get("subtitle_texts") for elem in segment.scene_elements
        )

    def _collect_story_scan_tasks(self, segment: ScriptSegment, seg_idx: int, audio_dir: Path) -> list[dict]:
        tasks = []
        for elem_idx, elem in enumerate(segment.scene_elements):
            subtitle_texts = elem.props.get("subtitle_texts", []) or []
            for sub_idx, sub_text in enumerate(subtitle_texts):
                sub_text = (sub_text or "").strip()
                if not sub_text:
                    continue
                audio_path = str(audio_dir / f"segment_{seg_idx:02d}_elem_{elem_idx:02d}_sub_{sub_idx:02d}.mp3")
                tasks.append(self._prepare_task(
                    text=sub_text,
                    audio_path=audio_path,
                    emotion=segment.emotion,
                    seg_idx=seg_idx,
                    elem_idx=elem_idx,
                    sub_idx=sub_idx,
                ))
        return tasks

    def _collect_segment_task(self, segment: ScriptSegment, idx: int, audio_dir: Path) -> dict | None:
        if not (segment.audio_text or "").strip():
            audio_path = str(audio_dir / f"segment_{idx:02d}.mp3")
            Path(audio_path).unlink(missing_ok=True)
            segment.actual_duration = 0.0
            segment.audio_path = ""
            return None

        audio_path = str(audio_dir / f"segment_{idx:02d}.mp3")
        return self._prepare_task(
            text=segment.audio_text,
            audio_path=audio_path,
            emotion=segment.emotion,
            seg_idx=idx,
            elem_idx=None,
            sub_idx=None,
        )

    def _prepare_task(self, *, text, audio_path, emotion, seg_idx, elem_idx, sub_idx) -> dict:
        task = {
            "text": text,
            "audio_path": audio_path,
            "emotion": emotion,
            "seg_idx": seg_idx,
            "elem_idx": elem_idx,
            "sub_idx": sub_idx,
            "result": None,
            "needs_synthesis": not Path(audio_path).exists(),
        }
        if not task["needs_synthesis"]:
            task["result"] = TTSResult(duration=get_audio_duration(audio_path))
        return task

    # ── Phase 2: execute synthesis in parallel ──

    def _execute_tasks(self, tasks: list[dict]) -> None:
        pending = [t for t in tasks if t["needs_synthesis"]]
        if not pending:
            self.logger.info("All TTS tasks cached, nothing to synthesize.")
            return

        self.logger.info(f"Synthesizing {len(pending)} TTS tasks (workers={self.max_workers})...")
        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.tts_provider.synthesize, t["text"], t["audio_path"], t.get("emotion")
                ): t
                for t in pending
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    task["result"] = future.result()
                except Exception as e:
                    self.logger.error(f"TTS synthesis failed for task [{task['seg_idx']}]: {e}")
                    raise
                completed += 1
                if completed % 5 == 0 or completed == len(pending):
                    self.logger.info(f"  TTS progress: {completed}/{len(pending)}")

    # ── Phase 3: assemble results back into script ──

    def _assemble_results(self, script: Script, tasks: list[dict], audio_dir: Path) -> None:
        from itertools import groupby
        tasks.sort(key=lambda t: t["seg_idx"])
        tasks_by_seg = {k: list(g) for k, g in groupby(tasks, key=lambda t: t["seg_idx"])}

        for seg_idx, segment in enumerate(script.segments):
            seg_tasks = tasks_by_seg.get(seg_idx, [])
            if not seg_tasks:
                continue

            if segment.segment_type == "story_scan" and self._has_per_card_audio(segment):
                self._assemble_story_scan(segment, seg_tasks)
            else:
                self._assemble_simple_segment(segment, seg_tasks[0])

    def _assemble_story_scan(self, segment: ScriptSegment, tasks: list[dict]) -> None:
        total_duration = 0.0
        all_cues = []

        from itertools import groupby
        tasks.sort(key=lambda t: t["elem_idx"])
        tasks_by_elem = {k: list(g) for k, g in groupby(tasks, key=lambda t: t["elem_idx"])}

        valid_tasks = [t for t in tasks if t["result"] is not None]
        total_subs = len(valid_tasks)
        sub_idx = 0

        for elem_idx, elem in enumerate(segment.scene_elements):
            elem_tasks = tasks_by_elem.get(elem_idx, [])
            elem_duration = 0.0
            for task in elem_tasks:
                result = task["result"]
                if result is None:
                    continue
                all_cues.append({
                    "text": task["text"],
                    "start_time": total_duration,
                    "end_time": total_duration + result.duration,
                    "audio_path": task["audio_path"],
                })
                total_duration += result.duration
                elem_duration += result.duration
                sub_idx += 1
                if sub_idx < total_subs and self.subtitle_gap > 0:
                    total_duration += self.subtitle_gap
                    elem_duration += self.subtitle_gap
            elem.props["audio_duration"] = elem_duration

        segment.actual_duration = total_duration
        segment.meta["subtitle_audios"] = all_cues
        segment.cues = [
            Cue(text=c["text"], start_time=c["start_time"], end_time=c["end_time"])
            for c in all_cues
        ]

    def _assemble_simple_segment(self, segment: ScriptSegment, task: dict) -> None:
        result = task["result"]
        if result is None:
            return
        segment.actual_duration = result.duration
        if segment.segment_type == "dashboard":
            segment.actual_duration = max(segment.estimated_duration, result.duration)
        segment.audio_path = task["audio_path"]
