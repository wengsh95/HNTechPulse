import json
from pathlib import Path

from src.core.interfaces import LLMProvider
from src.core.models import Script
from src.pipeline.content_preparer import ContentPreparer
from src.utils.logger import setup_logger


class TranslationManager:
    def __init__(self, llm_provider: LLMProvider, content_preparer: ContentPreparer, config: dict, debug: bool = False, level=None):
        self.llm_provider = llm_provider
        self.content_preparer = content_preparer
        self.config = config
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def translate(self, content, script, date: str):
        """Translate titles + referenced comments. Checkpointed.

        Runs after script generation so we know which comments are referenced
        in story cards. Updates both content (title_cn) and script (dashboard
        title_translation, viewpoint quote_cn) in place.
        """
        translations_path = Path(f"data/{date}/translations.json")

        # Checkpoint: reuse cached translations
        if translations_path.exists():
            self.logger.info(f"  Loading cached translations from {translations_path}")
            with open(translations_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
            for key, value in translations.items():
                if key.startswith("title_"):
                    idx = int(key.split("_", 1)[1])
                    if idx < len(content.items):
                        content.items[idx].title_cn = value
            self.apply_translations_to_script(script, content, translations)
            self.content_preparer.save_content(content, date)
            return content, script

        # 1. Translate all titles
        content = self.llm_provider.translate_titles(content, "translate.md")

        # 2. Collect referenced comments from story_scan cards
        comment_refs = self.collect_comment_refs(script)

        # 3. Translate only the referenced comments
        comment_translations = {}
        if comment_refs:
            comment_translations = self.llm_provider.translate_comments(content, comment_refs)

        # 4. Build checkpoint and apply to script
        translations = {}
        for idx, item in enumerate(content.items):
            if item.title_cn:
                translations[f"title_{idx}"] = item.title_cn
        translations.update(comment_translations)

        if translations:
            translations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(translations_path, "w", encoding="utf-8") as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
            self.logger.info(f"  Saved {len(translations)} translations to {translations_path}")

        self.apply_translations_to_script(script, content, translations)

        self.content_preparer.save_content(content, date)

        return content, script

    @staticmethod
    def collect_comment_refs(script) -> dict:
        """Collect {key: quote_text} from story_scan viewpoints."""
        refs = {}
        for seg in script.segments:
            if seg.segment_type != "story_scan":
                continue
            for elem in seg.scene_elements:
                if elem.element_type != "story_scan_card":
                    continue
                story_idx = elem.props.get("story_index")
                if story_idx is None:
                    continue
                for vp in elem.props.get("viewpoints", []):
                    ci = vp.get("comment_index")
                    quote = vp.get("quote", "")
                    if ci is not None and quote:
                        key = f"comment_{story_idx}_{ci}"
                        refs[key] = quote
        return refs

    @staticmethod
    def apply_translations_to_script(script, content, translations: dict) -> None:
        """Apply translations to script: dashboard title_cn and viewpoint quote_cn."""
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
                    if elem.element_type == "story_scan_card":
                        story_idx = elem.props.get("story_index")
                        for vp in elem.props.get("viewpoints", []):
                            ci = vp.get("comment_index")
                            if ci is not None and story_idx is not None:
                                key = f"comment_{story_idx}_{ci}"
                                if key in translations:
                                    vp["quote_cn"] = translations[key]
