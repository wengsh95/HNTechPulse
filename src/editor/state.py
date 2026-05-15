"""Load/save script.json and enrichment.json for the editor."""

import json
import shutil
from pathlib import Path
from typing import Optional


class EditorState:
    def __init__(self, date: str, data_dir: str = "data"):
        self.date = date
        self.data_dir = Path(data_dir)
        self.script: dict = {}
        self.content: dict = {}
        self.enrichment: dict = {}
        self._loaded = False

    def load(self) -> bool:
        base = self.data_dir / self.date
        script_path = base / "script.json"
        content_path = base / "content.json"
        enrichment_path = base / "enrichment.json"

        if not script_path.exists():
            return False

        self.script = _read_json(script_path)
        self.content = _read_json(content_path) if content_path.exists() else {}
        self.enrichment = (
            _read_json(enrichment_path) if enrichment_path.exists() else {}
        )
        self._loaded = True
        return True

    def save(self):
        base = self.data_dir / self.date
        base.mkdir(parents=True, exist_ok=True)
        _write_json(base / "script.json", self.script)

    # ── segment access ──────────────────────────────────────────

    def get_segment(self, segment_type: str) -> Optional[dict]:
        for seg in self.script.get("segments", []):
            if seg["segment_type"] == segment_type:
                return seg
        return None

    def get_stories(self) -> list[dict]:
        """Return list of {story_index, source_id, event_card, atmosphere_card}."""
        seg = self.get_segment("story_scan")
        if not seg:
            return []

        stories: dict[int, dict] = {}
        for elem in seg.get("scene_elements", []):
            etype = elem.get("element_type")
            if etype not in ("event_card", "atmosphere_card"):
                continue
            idx = elem.get("props", {}).get("story_index", 0)
            if idx not in stories:
                stories[idx] = {
                    "story_index": idx,
                    "source_id": self._story_index_to_source_id(idx),
                    "event_card": None,
                    "atmosphere_card": None,
                }
            stories[idx][etype] = elem

        # Return sorted by story_index
        return [stories[k] for k in sorted(stories)]

    def _story_index_to_source_id(self, story_index: int) -> str:
        items = self.content.get("items", [])
        if 0 <= story_index < len(items):
            return items[story_index].get("source_id", str(story_index))
        return str(story_index)

    # ── image access ────────────────────────────────────────────

    def get_image_candidates(self, source_id: str) -> list[dict]:
        """Return list of {path, source} from enrichment data."""
        items = self.enrichment.get("items", {})
        item = items.get(source_id, {})
        candidates = item.get("image_candidates", [])
        if not candidates:
            # fallback: build from article_images
            for p in item.get("article_images", []):
                candidates.append({"path": p, "source": "page"})
            if item.get("screenshot_image"):
                candidates.append(
                    {"path": item["screenshot_image"], "source": "screenshot"}
                )
        return candidates

    def get_story_title(self, source_id: str) -> str:
        items = self.content.get("items", [])
        for item in items:
            if item.get("source_id") == source_id:
                return item.get("title_cn") or item.get("title", "")
        return ""

    def get_article_data(self, source_id: str) -> dict:
        """Return {article_text, article_summary} for a source_id."""
        items = self.enrichment.get("items", {})
        return items.get(source_id, {})

    # ── image management ────────────────────────────────────────

    def add_image(self, source_id: str, file_path: str) -> str:
        """Copy uploaded image to images/ dir, add to candidates. Returns relative path."""
        base = self.data_dir / self.date
        images_dir = base / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        src = Path(file_path)
        suffix = src.suffix or ".jpg"
        dest_name = f"{source_id}_upload_{_timestamp()}{suffix}"
        dest = images_dir / dest_name
        shutil.copy2(file_path, dest)

        rel_path = f"images/{dest_name}"
        self._add_candidate(source_id, rel_path, "upload")
        return rel_path

    def _add_candidate(self, source_id: str, path: str, source: str):
        items = self.enrichment.setdefault("items", {})
        item = items.setdefault(source_id, {})
        candidates = item.setdefault("image_candidates", [])
        if not any(c.get("path") == path for c in candidates):
            candidates.append({"path": path, "source": source})
        if not item.get("article_images"):
            item["article_images"] = []
        if path not in item["article_images"]:
            item["article_images"].append(path)

    def reorder_images(self, source_id: str, paths: list[str]):
        """Replace article_images order for a source_id."""
        items = self.enrichment.setdefault("items", {})
        item = items.setdefault(source_id, {})
        item["article_images"] = paths

    def save_enrichment(self):
        base = self.data_dir / self.date
        base.mkdir(parents=True, exist_ok=True)
        _write_json(base / "enrichment.json", self.enrichment)


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")
