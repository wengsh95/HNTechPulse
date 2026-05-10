import json
from pathlib import Path

from src.core.interfaces import LLMProvider
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.comment_selection import (
    clean_comment_text,
    classify_comment_stance,
    comment_key,
    select_representative_comments,
)
from src.utils.logger import setup_logger


class TranslationManager:
    def __init__(self, llm_provider: LLMProvider, content_preparer: ContentPreparer, config: dict, debug: bool = False, level=None):
        self.llm_provider = llm_provider
        self.content_preparer = content_preparer
        self.config = config
        self.logger = setup_logger(__name__, debug=debug, level=level)

    @staticmethod
    def _classify_stance(comment) -> str:
        """Classify comment stance from VADER sentiment, matching _expand_quote_card."""
        return classify_comment_stance(comment)

    @staticmethod
    def _pick_stance_diverse(comments: list, max_n: int = 3) -> list:
        """Pick one top-quality comment per stance, then fill with remaining top comments."""
        return select_representative_comments(comments, max_n=max_n)

    def translate(self, content, script, date: str):
        """Translate titles + referenced comments. Checkpointed.

        Translates titles and one top-quality comment per stance per story
        (the same comments _expand_quote_card injects at render time).
        Updates content (title_cn, comment.content_cn) in place.
        """
        translations_path = Path(f"data/{date}/translations.json")
        translations = {}

        if translations_path.exists():
            self.logger.info(f"  Loading cached translations from {translations_path}")
            with open(translations_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
            for key, value in translations.items():
                if key.startswith("title_"):
                    idx = int(key.split("_", 1)[1])
                    if idx < len(content.items):
                        content.items[idx].title_cn = value
            self._apply_comment_translations(content, translations)
        else:
            # 1. Translate all titles
            content = self.llm_provider.translate_titles(content, "translate.md")
            for idx, item in enumerate(content.items):
                if item.title_cn:
                    translations[f"title_{idx}"] = item.title_cn

        # 2. Collect and translate stance-diverse comments (if not cached)
        comment_refs = self.collect_comment_refs(content)
        missing_comment_refs = {
            key: value
            for key, value in comment_refs.items()
            if key not in translations
        }

        if missing_comment_refs:
            comment_translations = self.llm_provider.translate_comments(content, missing_comment_refs)
            translations.update(comment_translations)
            self._apply_comment_translations(content, translations)

        # 3. Save checkpoint
        if translations:
            translations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(translations_path, "w", encoding="utf-8") as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
            self.logger.info(f"  Saved {len(translations)} translations to {translations_path}")

        self.apply_translations_to_script(script, content, translations)
        self.content_preparer.save_content(content, date)

        return content, script

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strip HTML tags and decode entities so the LLM translates clean text."""
        return clean_comment_text(text)

    @staticmethod
    def _comment_translation_key(story_idx: int, item, comment, selected_idx: int) -> str:
        return comment_key(story_idx, item.source_id, comment, selected_idx)

    @staticmethod
    def _legacy_comment_translation_key(story_idx: int, selected_idx: int) -> str:
        return f"comment_{story_idx}_{selected_idx}"

    def collect_comment_refs(self, content) -> dict:
        """Collect one top-quality comment per stance per story for translation.

        These are the same comments _expand_quote_card injects at render time,
        so translating them ensures QuoteCard displays Chinese text.
        """
        refs = {}
        for story_idx, item in enumerate(content.items):
            selected = self._pick_stance_diverse(item.comments)
            for i, c in enumerate(selected):
                if c.content:
                    key = self._comment_translation_key(story_idx, item, c, i)
                    refs[key] = self._clean_html(c.content)
        return refs

    def _apply_comment_translations(self, content, translations: dict) -> None:
        """Set content_cn on stance-diverse selected comments from translations."""
        for story_idx, item in enumerate(content.items):
            selected = self._pick_stance_diverse(item.comments)
            for selected_idx, comment in enumerate(selected):
                stable_key = self._comment_translation_key(story_idx, item, comment, selected_idx)
                legacy_key = self._legacy_comment_translation_key(story_idx, selected_idx)
                value = translations.get(stable_key) or translations.get(legacy_key)
                if value:
                    comment.content_cn = value

    @staticmethod
    def apply_translations_to_script(script, content, translations: dict) -> None:
        """Apply translations to script: dashboard title_cn and quote translations."""
        for seg in script.segments:
            if seg.segment_type == "dashboard":
                for elem in seg.scene_elements:
                    if elem.element_type == "dashboard_card":
                        for entry in elem.props.get("entries", []):
                            story_idx = entry.get("story_index")
                            if story_idx is not None and story_idx < len(content.items):
                                entry["title_translation"] = content.items[story_idx].title_cn
            elif seg.segment_type == "story_scan":
                for elem in seg.scene_elements:
                    if elem.element_type == "quote_card":
                        story_idx = elem.props.get("story_index")
                        for i, q in enumerate(elem.props.get("quotes", [])):
                            if story_idx is not None:
                                item = content.items[story_idx] if story_idx < len(content.items) else None
                                if item is None:
                                    continue
                                selected = TranslationManager._pick_stance_diverse(item.comments)
                                if i >= len(selected):
                                    continue
                                stable_key = TranslationManager._comment_translation_key(story_idx, item, selected[i], i)
                                legacy_key = TranslationManager._legacy_comment_translation_key(story_idx, i)
                                if stable_key in translations:
                                    q["text_cn"] = translations[stable_key]
                                elif legacy_key in translations:
                                    q["text_cn"] = translations[legacy_key]
