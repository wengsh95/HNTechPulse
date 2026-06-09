"""Tests for src/core/prompts.py."""

import pytest
from pathlib import Path

from src.core.prompts import render_prompt, _KNOWN_PLACEHOLDERS


class TestRenderPrompt:
    def test_single_placeholder(self):
        result = render_prompt("Date: {{ date }}", date="2026-06-05")
        assert result == "Date: 2026-06-05"

    def test_multiple_placeholders(self):
        template = "{{ title }} — {{ date }}"
        result = render_prompt(template, title="Hello", date="2026-06-05")
        assert result == "Hello — 2026-06-05"

    def test_repeated_placeholder(self):
        template = "{{ date }} and again {{ date }}"
        result = render_prompt(template, date="2026-06-05")
        assert result == "2026-06-05 and again 2026-06-05"

    def test_unknown_keyword_raises(self):
        with pytest.raises(ValueError, match="Unknown prompt placeholder"):
            render_prompt("{{ foo }}", foo="bar")

    def test_unknown_keyword_lists_all_invalid(self):
        with pytest.raises(ValueError, match="foo.*quux"):
            render_prompt("{{ foo }} {{ quux }}", foo="a", quux="b")

    def test_placeholder_in_template_but_not_in_kwargs_left_untouched(self):
        result = render_prompt("Date: {{ date }}", title="ignored")
        assert result == "Date: {{ date }}"

    def test_no_placeholders_identity(self):
        result = render_prompt("plain text no placeholders")
        assert result == "plain text no placeholders"

    def test_extra_known_placeholder_in_kwargs_silently_ignored(self):
        # story_json is a known placeholder but not in this template
        result = render_prompt("{{ date }}", date="2026-06-05", story_json="{}")
        assert result == "2026-06-05"

    def test_persona_left_for_multi_pass(self):
        # persona is commonly injected before the rest — test it's left untouched
        template = "{{ persona }}\nTitle: {{ title }}"
        result = render_prompt(template, title="My Title")
        assert result == "{{ persona }}\nTitle: My Title"

    def test_empty_values(self):
        result = render_prompt("{{ title }}", title="")
        assert result == ""


class TestKnownPlaceholders:
    """Verify all PH_* constants are consistent with _KNOWN_PLACEHOLDERS."""

    def test_all_constants_accounted_for(self):
        # Collect all PH_* values defined in prompts.py
        from src.core import prompts as mod

        ph_values = {
            v
            for k, v in vars(mod).items()
            if k.startswith("PH_") and isinstance(v, str)
        }
        assert ph_values == _KNOWN_PLACEHOLDERS

    def test_no_duplicate_ph_names(self):
        from src.core import prompts as mod

        ph_names = [
            k
            for k in vars(mod)
            if k.startswith("PH_") and isinstance(vars(mod)[k], str)
        ]
        assert len(ph_names) == len(set(ph_names))


class TestPublishGuidePrompt:
    def test_publish_guide_is_bilibili_only(self):
        text = Path("prompts/publish_guide.md").read_text(encoding="utf-8")

        assert "B 站" in text
        assert "YouTube" not in text
        assert "youtube" not in text.lower()
        assert "Tags" not in text
