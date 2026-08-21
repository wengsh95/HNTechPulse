from unittest.mock import MagicMock, patch

from tests.stage_fixtures import make_content, make_orchestrator, make_script


class TestQuickNewsStage:
    def test_quick_news_persists_video_structure_in_same_step(self):
        orch = make_orchestrator(dry_run=False)
        script = make_script()
        orch._normalize_video_structure = MagicMock(return_value=script)
        orch.script_writer.save_script = MagicMock()

        with patch("src.pipeline.stages.editorial.draft_quick_news") as draft:
            draft.return_value = MagicMock()
            result = orch._step_draft_quick_news(script, "2026-04-26")

        assert result is script
        orch._normalize_video_structure.assert_called_once_with(script, "2026-04-26")
        orch.script_writer.save_script.assert_called_once_with(script, "2026-04-26")

    def test_quick_news_applies_comment_translation_after_structure(self):
        orch = make_orchestrator(dry_run=False)
        script = make_script()
        content = make_content()
        orch._normalize_video_structure = MagicMock(return_value=script)
        orch._apply_comment_translations = MagicMock(return_value=(content, script))
        orch.script_writer.save_script = MagicMock()

        with patch("src.pipeline.stages.editorial.draft_quick_news"):
            result = orch._step_draft_quick_news(script, "2026-04-26", content=content)

        assert result is script
        orch._normalize_video_structure.assert_called_once_with(script, "2026-04-26")
        orch._apply_comment_translations.assert_called_once_with(
            content, script, "2026-04-26", save_script=False
        )


class TestEditorialHelpers:
    def test_parse_review_revisions_discards_invalid_entries(self):
        orch = make_orchestrator(dry_run=False)

        result = orch._parse_review_revisions(
            {
                "revisions": [
                    {"index": 0, "subtitle_texts": ["保留"]},
                    {"index": -1, "subtitle_texts": ["越界"]},
                    {"index": 3, "subtitle_texts": ["越界"]},
                    {"index": 1, "subtitle_texts": "不是列表"},
                    {"index": 2, "subtitle_texts": ["", "有效"]},
                ]
            },
            sub_segment_count=3,
        )

        assert result == {0: ["保留"], 2: ["有效"]}
