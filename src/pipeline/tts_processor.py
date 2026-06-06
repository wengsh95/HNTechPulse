import json
import subprocess
from hashlib import sha256
from pathlib import Path

from src.core.interfaces import TTSProvider
from src.core.models import Cue, Script, ScriptSegment
from src.pipeline.timing_engine import TimingEngine
from src.providers.renderer.binary_finder import find_ffmpeg
from src.utils.async_helper import run_async
from src.utils.audio import get_audio_duration
from src.utils.audio_alignment import AlignmentSegment, align_audio
from src.utils.atomic_io import atomic_write_json
from src.utils.logger import setup_logger

_FFMPEG = find_ffmpeg() or "ffmpeg"


class TTSProcessor:
    def __init__(
        self, tts_provider: TTSProvider, config: dict, debug: bool = False, level=None
    ):
        self.tts_provider = tts_provider
        self.config = config
        self.debug = debug
        timing_cfg = config.get("timing", {})
        self.timing_engine = TimingEngine(
            segment_gap=float(timing_cfg.get("segment_gap", 0.0)),
            debug=debug,
            level=level,
        )
        self.logger = setup_logger(__name__, debug=debug, level=level)
        tts_config = config.get("tts", {})
        self.audio_delay = float(timing_cfg.get("event_card_audio_delay", 0.0))
        self.sample_rate = int(tts_config.get("sample_rate", 24000))
        # Parallel TTS calls. Each TTS provider is a network request with
        # independent state; running N concurrent shaves the wall time
        # roughly by /N. Tune to the provider's rate limit (edge-tts ~6,
        # mimo/minimax lower — check your plan).
        self.tts_max_concurrent = max(1, int(tts_config.get("max_concurrent", 6)))
        self.whisper_model = tts_config.get("whisper_model", "large-v3")
        self.whisper_model_path = tts_config.get("whisper_model_path", "")
        if self.whisper_model_path and not Path(self.whisper_model_path).is_absolute():
            self.whisper_model_path = str(
                Path(__file__).resolve().parents[2] / self.whisper_model_path
            )

    def process_audio(self, script: Script, date: str, content=None) -> Script:
        """Synthesize audio and align subtitles via Whisper.

        story_scan segments: per-element TTS → concatenate → cues.
        Other segments: one TTS call → Whisper alignment → cues.
        """
        audio_dir = Path(f"data/{date}/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        self._synthesize_segments(script, audio_dir)

        self.timing_engine.compute_timeline(script)
        self.timing_engine.set_scene_element_times(script)
        self.timing_engine.validate_segment_duration(script)
        return script

    @staticmethod
    def _text_hash(text: str) -> str:
        return sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _manifest_path(audio_path: str) -> Path:
        return Path(audio_path).with_suffix(Path(audio_path).suffix + ".json")

    # ── Synthesis ──────────────────────────────────────────────────────

    def _synthesize_segments(self, script: Script, audio_dir: Path) -> None:
        """Synthesize audio for all segments.

        TTS calls (the network-bound part) run concurrently across the whole
        script — typically 6-9 independent edge-tts requests for one video,
        all in a single `asyncio.gather` batch with a `tts_max_concurrent`
        semaphore. Whisper alignment runs after the TTS batch so the singleton
        model is reused (no per-element reload). Per-segment finalization
        (ffmpeg concat for story_scan, segment.audio_path / cues for simple)
        happens after alignment.
        """
        # Phase 1: collect TTS jobs and pre-finalized cached results.
        # `tts_jobs` is the queue for new TTS work; `story_scan_elems` and
        # `simple_segs` track what each segment will need to finalize.
        tts_jobs: list[dict] = []
        story_scan_elems: dict[
            int, list[dict]
        ] = {}  # seg_idx -> per-element dicts (cached or pending)
        simple_segs: list[dict] = []  # simple segments needing TTS

        for seg_idx, segment in enumerate(script.segments):
            if segment.segment_type == "story_scan" and self._has_per_card_audio(
                segment
            ):
                elem_entries: list[dict] = []
                for elem_idx, elem in enumerate(segment.scene_elements):
                    subtitle_texts = elem.props.get("subtitle_texts", []) or []
                    texts = [t.strip() for t in subtitle_texts if t and t.strip()]
                    if not texts:
                        elem.props["audio_duration"] = 0.0
                        continue
                    combined = "\n\n".join(texts)
                    elem_audio_path = str(
                        audio_dir / f"segment_{seg_idx:02d}_elem_{elem_idx:02d}.mp3"
                    )
                    text_hash = self._text_hash(combined)
                    cached = self._load_segment_alignment(elem_audio_path, text_hash)
                    if cached is not None:
                        duration = get_audio_duration(elem_audio_path)
                        elem.props["audio_duration"] = duration
                        elem_entries.append(
                            {
                                "elem_idx": elem_idx,
                                "audio_path": elem_audio_path,
                                "ref_texts": texts,
                                "text_hash": text_hash,
                                "aligned": cached,
                                "duration": duration,
                                "needs_tts": False,
                            }
                        )
                    else:
                        elem_entries.append(
                            {
                                "elem_idx": elem_idx,
                                "audio_path": elem_audio_path,
                                "ref_texts": texts,
                                "text_hash": text_hash,
                                "aligned": None,
                                "duration": 0.0,
                                "needs_tts": True,
                            }
                        )
                        tts_jobs.append(
                            {
                                "seg_idx": seg_idx,
                                "elem_idx": elem_idx,
                                "text": combined,
                                "audio_path": elem_audio_path,
                                "emotion": None,
                            }
                        )
                if elem_entries:
                    story_scan_elems[seg_idx] = elem_entries
            else:
                # Simple (opening / closing / etc.)
                audio_text = (segment.audio_text or "").strip()
                if not audio_text:
                    segment.actual_duration = 0.0
                    segment.audio_path = ""
                    continue
                seg_audio_path = str(audio_dir / f"segment_{seg_idx:02d}.mp3")
                text_hash = self._text_hash(audio_text)
                cached = self._load_segment_alignment(seg_audio_path, text_hash)
                if cached is not None:
                    self._apply_simple_segment(segment, seg_audio_path, cached)
                else:
                    tts_jobs.append(
                        {
                            "seg_idx": seg_idx,
                            "elem_idx": None,
                            "text": audio_text,
                            "audio_path": seg_audio_path,
                            "emotion": segment.emotion,
                        }
                    )
                    simple_segs.append(
                        {
                            "seg_idx": seg_idx,
                            "audio_path": seg_audio_path,
                            "text_hash": text_hash,
                            "ref_texts": [audio_text],
                        }
                    )

        # Phase 2: TTS batch — one asyncio.gather covers all pending work.
        if tts_jobs:
            run_async(self._run_tts_batch(tts_jobs))

        # Phase 3: align newly-synthesized audio (serial; CPU bound and the
        # Whisper model is now cached so reloading is free).
        for job in tts_jobs:
            if job["elem_idx"] is None:
                ref_texts = [job["text"]]
            else:
                seg = script.segments[job["seg_idx"]]
                elem = seg.scene_elements[job["elem_idx"]]
                subtitle_texts = elem.props.get("subtitle_texts", []) or []
                ref_texts = [t.strip() for t in subtitle_texts if t and t.strip()]
            aligned = align_audio(
                job["audio_path"],
                ref_texts,
                model_size=self.whisper_model,
                model_path=self.whisper_model_path,
                debug=self.debug,
            )
            text_hash = self._text_hash(job["text"])
            self._write_segment_manifest(job["audio_path"], text_hash, aligned)
            duration = get_audio_duration(job["audio_path"])
            if job["elem_idx"] is not None:
                # Fill the per-element entry that finalize will consume.
                for entry in story_scan_elems[job["seg_idx"]]:
                    if entry["elem_idx"] == job["elem_idx"]:
                        entry["aligned"] = aligned
                        entry["duration"] = duration
                        break
                elem = script.segments[job["seg_idx"]].scene_elements[job["elem_idx"]]
                elem.props["audio_duration"] = duration
            else:
                simple_info = next(
                    s for s in simple_segs if s["seg_idx"] == job["seg_idx"]
                )
                simple_info["aligned"] = aligned
                simple_info["duration"] = duration

        # Phase 4: finalize segments.
        for seg_idx, elem_entries in story_scan_elems.items():
            self._finalize_story_scan(
                script.segments[seg_idx], seg_idx, audio_dir, elem_entries
            )
        for simple_info in simple_segs:
            self._apply_simple_segment(
                script.segments[simple_info["seg_idx"]],
                simple_info["audio_path"],
                simple_info["aligned"],
            )

    @staticmethod
    def _has_per_card_audio(segment: ScriptSegment) -> bool:
        return any(elem.props.get("subtitle_texts") for elem in segment.scene_elements)

    # ── Parallel TTS batch ─────────────────────────────────────────────

    async def _run_tts_batch(self, jobs: list[dict]) -> None:
        """Synthesize all queued TTS jobs concurrently.

        Wraps the provider's sync `synthesize` in `asyncio.to_thread` so the
        event loop stays responsive while N requests are in flight. A
        semaphore caps concurrency at `tts_max_concurrent` to respect
        provider rate limits.
        """
        import asyncio

        sem = asyncio.Semaphore(self.tts_max_concurrent)

        async def _one(job: dict) -> None:
            async with sem:
                # `to_thread` pushes the sync synthesize call onto the
                # default executor (threads). Providers are network-bound,
                # so threads are the right abstraction here.
                await asyncio.to_thread(
                    self.tts_provider.synthesize,
                    job["text"],
                    job["audio_path"],
                    job.get("emotion"),
                )

        await asyncio.gather(*(_one(j) for j in jobs))

    # ── Per-element synthesis (story_scan) ─────────────────────────────

    def _finalize_story_scan(
        self,
        segment: ScriptSegment,
        seg_idx: int,
        audio_dir: Path,
        elem_entries: list[dict],
    ) -> None:
        """Concat the per-element audio files into a single segment track.

        TTS and Whisper alignment have already been done for every element
        (see ``_synthesize_segments``). This method only handles the
        ffmpeg concat, the silence-before-each-card delay, and the cue /
        subtitle_audios construction.
        """
        elem_audio_entries: list[tuple[int, str, float, list[AlignmentSegment]]] = [
            (e["elem_idx"], e["audio_path"], e["duration"], e["aligned"])
            for e in elem_entries
        ]

        if not elem_audio_entries:
            segment.audio_path = ""
            segment.actual_duration = 0.0
            segment.cues = []
            return

        if not elem_audio_entries:
            segment.audio_path = ""
            segment.actual_duration = 0.0
            segment.cues = []
            return

        # Concatenate element audio into segment audio
        # Insert silence before each card's audio for breathing room
        seg_audio_path = str(audio_dir / f"segment_{seg_idx:02d}.mp3")
        silence_path = (
            str(audio_dir / "_card_delay_silence.mp3") if self.audio_delay > 0 else ""
        )
        # Generate silence and measure actual duration (MP3 frame alignment may
        # differ slightly from the configured value).
        delay = 0.0
        if self.audio_delay > 0:
            if not Path(silence_path).exists():
                self._generate_silence(silence_path, self.audio_delay)
            delay = get_audio_duration(silence_path)

        audio_files_to_concat: list[str] = []
        all_cues: list[Cue] = []
        subtitle_audios: list[dict] = []
        cue_offset = 0.0

        for _elem_idx, elem_audio_path, duration, aligned in elem_audio_entries:
            # Insert silence before this card's audio
            if delay > 0 and duration > 0:
                audio_files_to_concat.append(silence_path)

            audio_files_to_concat.append(elem_audio_path)

            # Cues offset: silence + accumulated prior content
            for alg in aligned:
                all_cues.append(
                    Cue(
                        text=alg.text,
                        start_time=round(cue_offset + delay + alg.start_time, 3),
                        end_time=round(cue_offset + delay + alg.end_time, 3),
                    )
                )

            # audio_duration includes delay so visual covers the silence period
            segment.scene_elements[_elem_idx].props["audio_duration"] = delay + duration

            subtitle_audios.append(
                {
                    "audio_path": elem_audio_path,
                    "start_time": round(cue_offset + delay, 3),
                    "end_time": round(cue_offset + delay + duration, 3),
                }
            )
            cue_offset += delay + duration

        self._concat_audio_files(audio_files_to_concat, seg_audio_path)
        segment.audio_path = seg_audio_path
        # Drive actual_duration from the per-subtitle cumulative offset, not
        # from the concatenated MP3: the top-level audio track is filtered out
        # for story_scan (HNTechPulseComposition uses subtitle_audios instead),
        # so the concat's frame-alignment drift would otherwise mis-time the
        # segment boundary and clip the last elem's audio into the next segment.
        segment.actual_duration = round(cue_offset, 3)
        segment.meta["subtitle_audios"] = subtitle_audios

        segment.cues = all_cues

        # Snap adjacent cue boundaries together (Whisper alignment can
        # leave both gaps from mutagen > Whisper end time and overlaps
        # from element-boundary silence being double-counted). End the
        # final cue at the full concatenated audio duration.
        if segment.cues and segment.actual_duration:
            for i in range(len(segment.cues) - 1):
                if segment.cues[i + 1].start_time != segment.cues[i].end_time:
                    segment.cues[i].end_time = segment.cues[i + 1].start_time
            segment.cues[-1].end_time = round(segment.actual_duration, 3)

    def _generate_silence(self, output_path: str, duration: float) -> None:
        """Generate a silent MP3 matching TTS output sample rate and channels."""
        if Path(output_path).exists():
            return
        subprocess.run(
            [
                _FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r={self.sample_rate}:cl=mono",
                "-t",
                str(duration),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                output_path,
            ],
            capture_output=True,
            check=True,
        )

    def _concat_audio_files(self, audio_paths: list[str], output_path: str) -> None:
        """Concatenate MP3 audio files with re-encoding for consistent sample rate."""
        concat_list = Path(output_path).with_suffix(".concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for path in audio_paths:
                abs_path = Path(path).absolute().as_posix()
                f.write(f"file '{abs_path}'\n")
        try:
            subprocess.run(
                [
                    _FFMPEG,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_list),
                    "-ar",
                    str(self.sample_rate),
                    "-ac",
                    "1",
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    output_path,
                ],
                capture_output=True,
                check=True,
            )
        finally:
            concat_list.unlink(missing_ok=True)

    # ── Simple segment synthesis (opening, closing, etc.) ──────────────

    def _apply_simple_segment(
        self,
        segment: ScriptSegment,
        audio_path: str,
        aligned: list[AlignmentSegment],
    ) -> None:
        """Set audio_path / actual_duration / cues from a known alignment.

        Used for both the cache-hit path (alignment loaded from disk) and the
        post-TTS path (alignment just produced by ``_synthesize_segments``).
        TTS itself is owned by the parallel batch.
        """
        segment.audio_path = audio_path
        segment.actual_duration = get_audio_duration(audio_path)
        segment.cues = [
            Cue(text=seg.text, start_time=seg.start_time, end_time=seg.end_time)
            for seg in aligned
        ]
        if segment.cues and segment.actual_duration:
            segment.cues[-1].end_time = round(segment.actual_duration, 3)

    def _load_segment_alignment(
        self, audio_path: str, text_hash: str
    ) -> list[AlignmentSegment] | None:
        """Return cached alignment segments, or None if re-synthesis needed."""
        if not Path(audio_path).exists():
            return None
        manifest_path = self._manifest_path(audio_path)
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if manifest.get("text_hash") != text_hash:
            return None
        segments_data = manifest.get("segments")
        if not segments_data:
            return None
        return [
            AlignmentSegment(
                text=s["text"],
                start_time=s["start_time"],
                end_time=s["end_time"],
            )
            for s in segments_data
        ]

    def _write_segment_manifest(
        self,
        audio_path: str,
        text_hash: str,
        aligned: list[AlignmentSegment],
    ) -> None:
        manifest_path = self._manifest_path(audio_path)
        manifest = {
            "text_hash": text_hash,
            "segments": [
                {
                    "text": seg.text,
                    "start_time": round(seg.start_time, 3),
                    "end_time": round(seg.end_time, 3),
                }
                for seg in aligned
            ],
        }
        atomic_write_json(manifest_path, manifest)
