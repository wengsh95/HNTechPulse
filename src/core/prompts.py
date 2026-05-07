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
PH_ARTICLE_TEXT = "article_text"

_KNOWN_PLACEHOLDERS = frozenset({
    PH_PERSONA, PH_DATE, PH_STORY_JSON, PH_ANALYSES_JSON, PH_SELECTION_JSON,
    PH_COMMENTS_JSON, PH_ITEMS_JSON, PH_TITLE, PH_ARTICLE_TEXT,
})


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
        result = result.replace(f"{{{{ {name} }}}}", value)
    return result
