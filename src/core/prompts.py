"""Prompt template placeholders and rendering.

All `{{ xxx }}` tokens used in prompts/*.md must be declared here as PH_*
constants. Call sites should use render_prompt() instead of string .replace()
so that typos in placeholder names raise instead of silently no-op-ing.

Adding a new placeholder:
  1. Add PH_FOO = "foo" below.
  2. Add PH_FOO to _KNOWN_PLACEHOLDERS.
  3. Use render_prompt(template, foo=value) at the call site.
"""

# === Placeholder names (the text between {{ and }} in prompts/*.md) ===
PH_PERSONA = "persona"
PH_DATE = "date"
PH_STORY_JSON = "story_json"
PH_ANALYSES_JSON = "analyses_json"
PH_SELECTION_JSON = "selection_json"
PH_COMMENTS_JSON = "comments_json"
PH_ITEMS_JSON = "items_json"
PH_TITLE = "title"
PH_TITLE_CN = "title_cn"
PH_ARTICLE_TEXT = "article_text"
PH_ARTICLE_SUMMARY = "article_summary"
PH_EDITOR_ANGLE = "editor_angle"
PH_KEYWORDS = "keywords"
PH_URL = "url"
PH_CANDIDATES_JSON = "candidates_json"
PH_STORY_INDEX = "story_index"
PH_STORIES_JSON = "stories_json"
PH_HIGHLIGHT_ENTRIES = "highlight_entries"
PH_FOCUS_STORY_JSON = "focus_story_json"
PH_SCRIPT_TITLE = "script_title"
PH_SCRIPT_DESCRIPTION = "script_description"
PH_TITLE_CANDIDATES_JSON = "title_candidates_json"
PH_DATE_DISPLAY = "date_display"
PH_OTHER_STORIES_JSON = "other_stories_json"
PH_SUBSEGMENTS_JSON = "subsegments_json"
PH_QUOTES_JSON = "quotes_json"
PH_SCRIPT_JSON = "script_json"
PH_TEMPLATE_CATALOG_JSON = "template_catalog_json"

_KNOWN_PLACEHOLDERS = frozenset(
    {
        PH_PERSONA,
        PH_DATE,
        PH_STORY_JSON,
        PH_ANALYSES_JSON,
        PH_SELECTION_JSON,
        PH_COMMENTS_JSON,
        PH_ITEMS_JSON,
        PH_TITLE,
        PH_TITLE_CN,
        PH_ARTICLE_TEXT,
        PH_ARTICLE_SUMMARY,
        PH_EDITOR_ANGLE,
        PH_KEYWORDS,
        PH_URL,
        PH_CANDIDATES_JSON,
        PH_STORY_INDEX,
        PH_STORIES_JSON,
        PH_HIGHLIGHT_ENTRIES,
        PH_FOCUS_STORY_JSON,
        PH_SCRIPT_TITLE,
        PH_SCRIPT_DESCRIPTION,
        PH_TITLE_CANDIDATES_JSON,
        PH_DATE_DISPLAY,
        PH_OTHER_STORIES_JSON,
        PH_SUBSEGMENTS_JSON,
        PH_QUOTES_JSON,
        PH_SCRIPT_JSON,
        PH_TEMPLATE_CATALOG_JSON,
    }
)


def render_prompt(template: str, **values: str) -> str:
    """Substitute `{{ name }}` placeholders in a template.

    Only names listed in _KNOWN_PLACEHOLDERS are accepted as kwargs — passing
    an unknown key raises ValueError, which surfaces typos early.

    Placeholders that appear in the template but are not supplied in kwargs are
    left untouched (useful for multi-pass rendering, e.g. persona is injected
    before the rest of the values).
    """
    unknown = set(values) - _KNOWN_PLACEHOLDERS
    if unknown:
        raise ValueError(
            f"Unknown prompt placeholder(s): {sorted(unknown)}. "
            f"Declare them in src/core/prompts.py if intentional."
        )
    result = template
    for name, value in values.items():
        result = result.replace(f"{{{{ {name} }}}}", str(value))
    return result
