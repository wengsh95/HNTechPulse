import json
from pathlib import Path

from src.core.interfaces import LLMProvider
from src.pipeline.content_io import ContentPreparer
from src.pipeline.comment import (
    clean_comment_text,
    comment_key,
    select_quote_comments,
)
from src.pipeline.comment import (
    comment_judgement_key,
    load_comment_judgements,
)
from src.utils.logger import setup_logger


class TranslationManager:
    def __init__(
        self,
        llm_provider: LLMProvider,
        content_preparer: ContentPreparer,
        config: dict,
        debug: bool = False,
        level=None,
    ):
        self.llm_provider = llm_provider
        self.content_preparer = content_preparer
        self.config = config
        self.logger = setup_logger(__name__, debug=debug, level=level)

    @staticmethod
    def _selected_ids_by_story(script) -> dict[int, list[str]]:
        selected: dict[int, list[str]] = {}
        if script is None:
            return selected
        for seg in script.segments:
            if seg.segment_type != "story_scan":
                continue
            for elem in seg.scene_elements:
                if elem.element_type != "atmosphere_card":
                    continue
                story_idx = elem.props.get("story_index")
                if story_idx is None:
                    continue
                selected[story_idx] = elem.props.get("selected_comment_ids") or []
        return selected

    @staticmethod
    def _pick_quote_comments(
        comments: list, selected_ids=None, max_n: int = 3, judgement: dict | None = None
    ) -> list:
        """Pick the same comments the renderer will inject into AtmosphereCard."""
        return select_quote_comments(
            comments,
            selected_ids=selected_ids or [],
            judgement=judgement or {},
            max_n=max_n,
        )

    def translate(self, content, script, date: str):
        """Translate titles + referenced comments. Checkpointed.

        Translates titles and one top-quality comment per stance per story
        (the same comments _expand_atmosphere_card injects at render time).
        Updates content (title_cn, comment.content_cn) in place.
        """
        translations_path = Path(f"data/{date}/translations.json")
        translations = {}
        # Load judgements once for the entire translate step
        judgements = load_comment_judgements(content.date)

        if translations_path.exists():
            self.logger.info(f"  Loading cached translations from {translations_path}")
            with open(translations_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
            # Apply title translations by source_id, falling back to index for legacy caches
            items_by_source_id = {
                item.source_id: item for item in content.items if item.source_id
            }
            for key, value in translations.items():
                if key.startswith("title_"):
                    parts = key.split("_", 1)
                    if len(parts) < 2:
                        continue
                    token = parts[1]
                    # Prefer source_id-based key (title_<source_id>)
                    item = items_by_source_id.get(token)
                    if item is None:
                        # Fallback: legacy positional index key
                        try:
                            idx = int(token)
                            if idx < len(content.items):
                                item = content.items[idx]
                        except ValueError:
                            continue
                    if item is not None:
                        item.title_cn = value
            selected_ids_by_story = self._selected_ids_by_story(script)
            self._apply_comment_translations(
                content, translations, selected_ids_by_story, judgements
            )
        else:
            # 1. Translate titles (skip if already translated during enrich step)
            items_needing_translation = [
                item for item in content.items if item.title and not item.title_cn
            ]
            if items_needing_translation:
                content = self.llm_provider.translate_titles(content, "translate.md")
            else:
                self.logger.info("  All titles already translated, skipping")
            for idx, item in enumerate(content.items):
                if item.title_cn:
                    # Store by source_id for stable cache keys; keep index key for backward compat
                    if item.source_id:
                        translations[f"title_{item.source_id}"] = item.title_cn
                    translations[f"title_{idx}"] = item.title_cn

        # 2. Collect and translate stance-diverse comments (if not cached)
        selected_ids_by_story = self._selected_ids_by_story(script)
        comment_refs = self.collect_comment_refs(
            content, selected_ids_by_story, judgements
        )
        missing_comment_refs = {
            key: value for key, value in comment_refs.items() if key not in translations
        }

        if missing_comment_refs:
            comment_translations = self.llm_provider.translate_comments(
                content, missing_comment_refs
            )
            translations.update(comment_translations)
            self._apply_comment_translations(
                content, translations, selected_ids_by_story, judgements
            )

        # 3. Save checkpoint
        if translations:
            translations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(translations_path, "w", encoding="utf-8") as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
            self.logger.info(
                f"  Saved {len(translations)} translations to {translations_path}"
            )

        self.apply_translations_to_script(script, content, translations)
        self.content_preparer.save_content(content, date)

        return content, script

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strip HTML tags and decode entities so the LLM translates clean text."""
        return clean_comment_text(text)

    @staticmethod
    def _comment_translation_key(
        story_idx: int, item, comment, selected_idx: int
    ) -> str:
        return comment_key(story_idx, item.source_id, comment, selected_idx)

    @staticmethod
    def _legacy_comment_translation_key(story_idx: int, selected_idx: int) -> str:
        return f"comment_{story_idx}_{selected_idx}"

    def collect_comment_refs(
        self,
        content,
        selected_ids_by_story: dict | None = None,
        judgements: dict | None = None,
    ) -> dict:
        """Collect the exact comments AtmosphereCard will display for translation.

        LLM-selected ids are honored first, then the shared fallback selector fills
        to three quotable comments (one per stance: 支持/质疑/中立).
        """
        selected_ids_by_story = selected_ids_by_story or {}
        if judgements is None:
            judgements = load_comment_judgements(content.date)
        refs = {}
        for story_idx, item in enumerate(content.items):
            selected = self._pick_quote_comments(
                item.comments,
                selected_ids_by_story.get(story_idx, []),
                max_n=3,
                judgement=judgements.get(comment_judgement_key(item), {}),
            )
            for i, c in enumerate(selected):
                if c.content:
                    key = self._comment_translation_key(story_idx, item, c, i)
                    refs[key] = self._clean_html(c.content)
        return refs

    def _apply_comment_translations(
        self,
        content,
        translations: dict,
        selected_ids_by_story: dict | None = None,
        judgements: dict | None = None,
    ) -> None:
        """Set content_cn on the same comments AtmosphereCard will display."""
        selected_ids_by_story = selected_ids_by_story or {}
        if judgements is None:
            judgements = load_comment_judgements(content.date)
        for story_idx, item in enumerate(content.items):
            selected = self._pick_quote_comments(
                item.comments,
                selected_ids_by_story.get(story_idx, []),
                judgement=judgements.get(comment_judgement_key(item), {}),
            )
            for selected_idx, comment in enumerate(selected):
                stable_key = self._comment_translation_key(
                    story_idx, item, comment, selected_idx
                )
                legacy_key = self._legacy_comment_translation_key(
                    story_idx, selected_idx
                )
                value = translations.get(stable_key) or translations.get(legacy_key)
                if value:
                    comment.content_cn = value

    @staticmethod
    def apply_translations_to_script(script, content, translations: dict) -> None:
        """Apply title and quote translations to generated script props."""
        judgements = load_comment_judgements(content.date)
        for seg in script.segments:
            if seg.segment_type == "opening":
                for elem in seg.scene_elements:
                    if elem.element_type != "cover_card":
                        continue
                    for entry in elem.props.get("highlight_entries", []):
                        story_idx = entry.get("story_index")
                        if story_idx is not None and story_idx < len(content.items):
                            entry["title_translation"] = content.items[
                                story_idx
                            ].title_cn
            elif seg.segment_type == "story_scan":
                for elem in seg.scene_elements:
                    if elem.element_type == "atmosphere_card":
                        story_idx = elem.props.get("story_index")
                        for i, q in enumerate(elem.props.get("quotes", [])):
                            if story_idx is not None:
                                item = (
                                    content.items[story_idx]
                                    if story_idx < len(content.items)
                                    else None
                                )
                                if item is None:
                                    continue
                                selected = TranslationManager._pick_quote_comments(
                                    item.comments,
                                    elem.props.get("selected_comment_ids") or [],
                                    judgement=judgements.get(
                                        comment_judgement_key(item), {}
                                    ),
                                )
                                if i >= len(selected):
                                    continue
                                stable_key = (
                                    TranslationManager._comment_translation_key(
                                        story_idx, item, selected[i], i
                                    )
                                )
                                legacy_key = (
                                    TranslationManager._legacy_comment_translation_key(
                                        story_idx, i
                                    )
                                )
                                if stable_key in translations:
                                    q["text_cn"] = translations[stable_key]
                                elif legacy_key in translations:
                                    q["text_cn"] = translations[legacy_key]
