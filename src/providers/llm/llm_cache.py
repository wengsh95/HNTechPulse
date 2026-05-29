import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.models import ScriptSegment, SceneElement


class LLMCache:
    """Segment-level cache for LLM-generated script segments."""

    def __init__(self, logger, cache_schema_version: int = 4):
        self.logger = logger
        self.cache_schema_version = cache_schema_version

    def get_segment_cache_path(
        self, date: str, segment_type: str, story_index: int
    ) -> Path:
        cache_dir = Path(f"data/{date}/segments")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{segment_type}_{story_index}.json"

    def load_cached_segment(
        self,
        date: str,
        segment_type: str,
        story_index: int,
        expected_cache_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScriptSegment]:
        cache_path = self.get_segment_cache_path(date, segment_type, story_index)
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                seg_dict = json.load(f)
            cache_meta = seg_dict.get("_cache")
            if expected_cache_meta is not None and cache_meta != expected_cache_meta:
                self.logger.info(
                    f"    [{segment_type}_{story_index}] Cached segment metadata changed; regenerating"
                )
                return None
            scene_elements = [
                SceneElement(
                    element_type=e["element_type"],
                    start_time=e.get("start_time", 0.0),
                    end_time=e.get("end_time", 0.0),
                    props=e["props"],
                    sub_segment_index=e.get("sub_segment_index"),
                )
                for e in seg_dict.get("scene_elements", [])
            ]
            segment = ScriptSegment(
                segment_type=seg_dict["segment_type"],
                audio_text=seg_dict["audio_text"],
                duration=seg_dict.get(
                    "duration", seg_dict.get("estimated_duration", 0.0)
                ),
                scene_elements=scene_elements,
                meta=seg_dict.get("meta", {}),
            )
            return segment
        except Exception as e:
            self.logger.warning(f"    Failed to load cached segment: {e}")
            return None

    def save_segment_cache(
        self,
        date: str,
        segment_type: str,
        story_index: int,
        segment: ScriptSegment,
        cache_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        cache_path = self.get_segment_cache_path(date, segment_type, story_index)
        seg_dict = {
            "_cache": cache_meta or {},
            "segment_type": segment.segment_type,
            "audio_text": segment.audio_text,
            "duration": segment.duration,
            "scene_elements": [
                {
                    "element_type": e.element_type,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "props": e.props,
                    "sub_segment_index": e.sub_segment_index,
                }
                for e in segment.scene_elements
            ],
            "meta": segment.meta,
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(seg_dict, f, ensure_ascii=False, indent=2)

    def build_segment_cache_meta(
        self,
        *,
        prompt: str,
        story_id: Any,
        model: str,
        temperature: float,
    ) -> Dict[str, Any]:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return {
            "schema_version": self.cache_schema_version,
            "model": model,
            "temperature": temperature,
            "story_id": str(story_id),
            "prompt_hash": prompt_hash,
        }
