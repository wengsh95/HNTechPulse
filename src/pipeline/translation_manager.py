import html
import json
import re
from pathlib import Path

from src.core.interfaces import LLMProvider
from src.core.models import Script
from src.pipeline.content_preparer import ContentPreparer
from src.utils.logger import setup_logger

_HTML_TAG_RE = re.compile(r"<[^>]*>")


class TranslationManager:
    def __init__(self, llm_provider: LLMProvider, content_preparer: ContentPreparer, config: dict, debug: bool = False, level=None):
        self.llm_provider = llm_provider
        self.content_preparer = content_preparer
        self.config = config
        self.logger = setup_logger(__name__, debug=debug, level=level)

    @staticmethod
    def _classify_stance(comment) -> str:
        """Classify comment stance from VADER sentiment, matching _expand_quote_card."""
        sentiment = comment.sentiment or 0.0
        if sentiment > 0.3:
            return "支持"
        if sentiment < -0.3:
            return "质疑"
        return "中立"

    @staticmethod
    def _pick_stance_diverse(comments: list, max_n: int = 3) -> list:
        """Pick one top-quality comment per stance, then fill with remaining top comments."""
        scored = [c for c in comments if (c.quality_score or 0) > 0]
        scored.sort(key=lambda c: c.quality_score or 0, reverse=True)

        selected = []
        seen_stances = set()
        for c in scored:
            stance = TranslationManager._classify_stance(c)
            if stance in seen_stances:
                continue
            selected.append(c)
            seen_stances.add(stance)
            if len(selected) >= max_n:
                break

        # Fill up to at least 2 if stance diversity didn't yield enough
        if len(selected) < 2:
            for c in scored:
                if c not in selected:
                    selected.append(c)
                if len(selected) >= 2:
                    break

        return selected

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
        has_comment = any(k.startswith("comment_") for k in translations)

        if comment_refs and not has_comment:
            comment_translations = self.llm_provider.translate_comments(content, comment_refs)
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
        text = _HTML_TAG_RE.sub(" ", text)
        return html.unescape(text).strip()

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
                    key = f"comment_{story_idx}_{i}"
                    refs[key] = self._clean_html(c.content)
        return refs

    def _apply_comment_translations(self, content, translations: dict) -> None:
        """Set content_cn on stance-diverse selected comments from translations."""
        for key, value in translations.items():
            if not key.startswith("comment_"):
                continue
            parts = key.split("_")
            if len(parts) != 3:
                continue
            try:
                story_idx = int(parts[1])
                comment_idx = int(parts[2])
            except ValueError:
                continue
            if story_idx >= len(content.items):
                continue
            item = content.items[story_idx]
            selected = self._pick_stance_diverse(item.comments)
            if comment_idx < len(selected):
                selected[comment_idx].content_cn = value

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
                                key = f"comment_{story_idx}_{i}"
                                if key in translations:
                                    q["text_cn"] = translations[key]
