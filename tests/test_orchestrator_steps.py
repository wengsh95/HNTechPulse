import json
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script, ScriptSegment
from src.core.models import ContentComment, ContentItem
from src.pipeline.orchestrator import (
    DEFAULT_STEPS,
    Orchestrator,
    PIPELINE_STEPS,
    STANDALONE_STEPS,
    _resolve_steps,
)
from src.pipeline.human_review import (
    approve_current_script,
    generate_script_review_page,
)
from src.pipeline.script.io import save_script, save_script_to_path
from src.workflow.machine import WorkflowMachine
from src.workflow.video import VIDEO_WORKFLOW_STEPS


# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 3},
        "llm": {"model": "test-model", "fast_model": "test-fast"},
    }


def _make_orchestrator(dry_run=True):
    config = _make_config()
    return Orchestrator(
        config=config,
        content_fetcher=MagicMock(spec=ContentFetcher),
        llm_provider=MagicMock(spec=LLMProvider),
        tts_provider=MagicMock(spec=TTSProvider),
        renderer=MagicMock(spec=Renderer),
        debug=True,
        dry_run=dry_run,
    )


def _make_content():
    return ContentPackage(date="2026-04-26", items=[])


def _make_failed_content():
    return ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="123",
                title="Failed Story",
                url="https://example.com/failed",
                enrichment_source="fetch_failed",
            )
        ],
    )


def _make_failed_content_with_comments():
    content = _make_failed_content()
    content.items[0].comments = [
        ContentComment(author=f"u{i}", content=f"substantial comment {i}")
        for i in range(5)
    ]
    return content


def _make_script():
    return Script(
        title="T",
        description="D",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="hi", duration=1.0)],
    )


# ── Step list constants ─────────────────────────────────────────────────


class TestStepList:
    def test_pipeline_steps_in_expected_order(self):
        expected = [
            "fetch",
            "prefilter",
            "fetch_comments",
            "enrich_articles",
            "judge_comments",
            "write_script",
            "draft_quick_news",
            "prepare_story_images",
            "title",
            "cover_image",
            "cover_thumbnail",
            "draft_storyboard",
            "human_review",
            "apply_storyboard",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
        ]
        assert PIPELINE_STEPS == expected

    def test_standalone_is_render(self):
        assert STANDALONE_STEPS == {"render", "preview"}

    def test_default_steps_are_full_video_chain(self):
        assert DEFAULT_STEPS[-1] == "render"
        assert "write_script" in DEFAULT_STEPS
        assert "synthesize_audio" in DEFAULT_STEPS

    def test_default_chain_resolves_without_expansion(self):
        resolved = _resolve_steps(DEFAULT_STEPS)
        assert resolved == DEFAULT_STEPS

    def test_removed_compatibility_steps_are_rejected(self):
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            _resolve_steps(["translate_titles"])
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            _resolve_steps(["analyze_comments"])
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            _resolve_steps(["normalize_video_structure"])
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            _resolve_steps(["translate_comments"])
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            _resolve_steps(["publish_guide"])

    def test_optional_cover_thumbnail_expands_to_cover_image_only(self):
        assert _resolve_steps(["cover_thumbnail"]) == [
            "cover_image",
            "cover_thumbnail",
            "human_review",
        ]

    def test_prepare_render_auto_pulls_synthesize_audio(self):
        resolved = _resolve_steps(["prepare_render", "render"])
        assert "synthesize_audio" in resolved
        assert "prepare_render" in resolved
        assert "render" in resolved
        assert resolved.index("synthesize_audio") < resolved.index("prepare_render")
        assert resolved.index("prepare_subtitles") < resolved.index("synthesize_audio")

    def test_video_downstream_recovery_does_not_expand_editorial_chain(self):
        resolved = _resolve_steps(["synthesize_audio", "prepare_render", "render"])
        assert resolved == [
            "human_review",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]
        assert "write_script" not in resolved
        assert "review_script" not in resolved
        assert "fetch" not in resolved

    def test_render_only_still_requires_human_approval_gate(self):
        assert _resolve_steps(["render"]) == ["human_review", "render"]


# ── Per-step behaviour ──────────────────────────────────────────────────


class TestStepFetch:
    def test_dry_run_returns_empty_package(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_fetch("2026-04-26")
        assert isinstance(result, ContentPackage)
        assert result.date == "2026-04-26"
        assert len(result.items) == 0

    def test_agent_fetch_reuses_locked_selection(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        fetcher = MagicMock(spec=ContentFetcher)
        orch = Orchestrator(
            config=config,
            content_fetcher=fetcher,
            llm_provider=MagicMock(spec=LLMProvider),
            tts_provider=MagicMock(spec=TTSProvider),
            renderer=MagicMock(spec=Renderer),
            agent_mode=True,
        )
        content = ContentPackage(
            date="2026-04-26",
            items=[
                ContentItem(
                    source="hackernews",
                    source_id="101",
                    title="Locked story 1",
                    url="https://example.com/1",
                ),
                ContentItem(
                    source="hackernews",
                    source_id="202",
                    title="Locked story 2",
                    url="https://example.com/2",
                ),
            ],
        )
        orch.content_preparer.save_content(content, content.date)
        orch._write_selection_lock(content, content.date)

        result = orch._step_fetch(content.date)

        assert [item.source_id for item in result.items] == ["101", "202"]
        fetcher.fetch.assert_not_called()

    def test_agent_fetch_rejects_selection_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = Orchestrator(
            config=_make_config(),
            content_fetcher=MagicMock(spec=ContentFetcher),
            llm_provider=MagicMock(spec=LLMProvider),
            tts_provider=MagicMock(spec=TTSProvider),
            renderer=MagicMock(spec=Renderer),
            agent_mode=True,
        )
        locked = ContentPackage(
            date="2026-04-26",
            items=[
                ContentItem(
                    source="hackernews",
                    source_id="101",
                    title="Locked story",
                    url="https://example.com/1",
                )
            ],
        )
        changed = ContentPackage(
            date=locked.date,
            items=[
                ContentItem(
                    source="hackernews",
                    source_id="999",
                    title="Changed story",
                    url="https://example.com/9",
                )
            ],
        )
        orch.content_preparer.save_content(locked, locked.date)
        orch._write_selection_lock(locked, locked.date)
        orch.content_preparer.save_content(changed, changed.date)

        with pytest.raises(RuntimeError, match="Selection lock mismatch"):
            orch._step_fetch(changed.date)


class TestScriptLock:
    def test_manual_script_change_blocks_script_regeneration(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        script = _make_script()
        save_script(script, date)
        path = Path(f"data/{date[:7]}/{date}/pipeline/script.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["segments"][0]["audio_text"] = "手工改过的旁白"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        orch = _make_orchestrator(dry_run=True)
        with pytest.raises(RuntimeError, match="script.json changed"):
            orch._step_write_script(_make_content(), date)

    def test_script_without_lock_blocks_regeneration(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        script = _make_script()
        path = Path(f"data/{date[:7]}/{date}/pipeline/script.json")
        save_script_to_path(script, path, date=date)
        orch = _make_orchestrator(dry_run=True)
        orch.agent_mode = True
        with pytest.raises(RuntimeError, match="no script_lock.json"):
            orch._step_write_script(_make_content(), date)


class TestStepPrefilter:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_prefilter(content, "2026-04-26") is content

    def test_prefilter_cache_is_validated_by_prefilter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "2026-04" / "2026-04-26" / "pipeline").mkdir(parents=True)
        (
            tmp_path / "data" / "2026-04" / "2026-04-26" / "pipeline" / "content.json"
        ).write_text('{"items":[]}')
        (
            tmp_path / "data" / "2026-04" / "2026-04-26" / "pipeline" / "prefilter.json"
        ).write_text("{}")

        orch = _make_orchestrator(dry_run=False)
        orch.config["prefilter"] = {"comment_preview_enabled": False}
        orch.prefilter = MagicMock()
        content = _make_content()
        orch.prefilter.filter.return_value = content
        result = orch._step_prefilter(content, "2026-04-26")
        assert result is content
        orch.prefilter.filter.assert_called_once_with(content, "2026-04-26")

    def test_fetches_comment_preview_before_prefilter(self):
        orch = _make_orchestrator(dry_run=False)
        orch.config["prefilter"] = {
            "comment_preview_enabled": True,
            "comment_preview_count": 3,
        }
        content = _make_failed_content()
        orch.content_fetcher.fetch_comment_preview = MagicMock(return_value=content)
        orch.prefilter = MagicMock()
        orch.prefilter.filter.return_value = content
        orch.content_preparer = MagicMock()

        result = orch._step_prefilter(content, "2026-04-26")

        assert result is content
        orch.content_fetcher.fetch_comment_preview.assert_called_once_with(
            content,
            "2026-04-26",
            top_level_count=3,
        )
        orch.prefilter.filter.assert_called_once_with(content, "2026-04-26")


class TestStepFetchComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_fetch_comments(content, "2026-04-26") is content

    def test_partial_comments_do_not_skip_full_fetch(self):
        orch = _make_orchestrator(dry_run=False)
        content = _make_failed_content_with_comments()
        content.items[0].comments_partial = True
        orch.content_fetcher.fetch_comments = MagicMock(return_value=content)
        orch.content_preparer = MagicMock()

        result = orch._step_fetch_comments(content, "2026-04-26")

        assert result is content
        orch.content_fetcher.fetch_comments.assert_called_once_with(
            content,
            "2026-04-26",
        )


class TestStepEnrichArticles:
    def test_dry_run_returns_empty_failure_list(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        out, failed = orch._step_enrich_articles(content, "2026-04-26")
        assert out is content
        assert failed == []

    def test_no_enricher_returns_empty_failure_list(self):
        orch = _make_orchestrator(dry_run=False)
        orch.article_enricher = None
        content = _make_content()
        out, failed = orch._step_enrich_articles(content, "2026-04-26")
        assert out is content
        assert failed == []

    def test_successful_enrichment_owns_title_translation(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        item = ContentItem(
            source="hackernews",
            source_id="100",
            title="An English title",
            url="https://example.com",
            enrichment_source="downloaded_page",
        )
        content = ContentPackage(date="2026-04-26", items=[item])
        enricher = MagicMock()
        enricher.enrich.return_value = content
        orch.article_enricher = enricher
        orch.llm_provider.translate_titles.return_value = content

        out, failed = orch._step_enrich_articles(content, "2026-04-26")

        assert out is content
        assert failed == []
        orch.llm_provider.translate_titles.assert_called_once_with(
            content, "translate.md", "2026-04-26"
        )

    def test_degraded_enrichment_still_translates_titles(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.allow_degraded_enrichment = True
        item = ContentItem(
            source="hackernews",
            source_id="100",
            title="An English title",
            url="https://example.com",
            enrichment_source="fetch_failed",
        )
        content = ContentPackage(date="2026-04-26", items=[item])
        enricher = MagicMock()
        enricher.enrich.return_value = content
        orch.article_enricher = enricher
        orch.llm_provider.translate_titles.return_value = content

        out, failed = orch._step_enrich_articles(content, "2026-04-26")

        assert out is content
        assert [item.source_id for item in failed] == ["100"]
        orch.llm_provider.translate_titles.assert_called_once()


class TestStepJudgeComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_judge_comments(content, "2026-04-26") is content


class TestStepHumanReview:
    def test_human_review_prepares_automatic_copy_review(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        script = _make_script()
        content = _make_content()
        orch._auto_review_script = MagicMock(return_value=script)

        approved, review_page = orch._step_human_review(
            script, "2026-04-26", content=content
        )

        assert approved is False
        assert review_page.exists()
        orch._auto_review_script.assert_called_once_with(content, script, "2026-04-26")


class TestStepWriteScript:
    def test_dry_run_returns_test_script(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        result = orch._step_write_script(content, "2026-04-26")
        assert isinstance(result, Script)
        assert len(result.segments) >= 1
        assert result.segments[0].segment_type == "opening"


class TestStepQuickNews:
    def test_quick_news_persists_video_structure_in_same_step(self):
        orch = _make_orchestrator(dry_run=False)
        script = _make_script()
        orch._normalize_video_structure = MagicMock(return_value=script)
        orch.script_writer.save_script = MagicMock()

        with patch("src.pipeline.stages.editorial.draft_quick_news") as draft:
            draft.return_value = MagicMock()
            result = orch._step_draft_quick_news(script, "2026-04-26")

        assert result is script
        orch._normalize_video_structure.assert_called_once_with(script, "2026-04-26")
        orch.script_writer.save_script.assert_called_once_with(script, "2026-04-26")

    def test_quick_news_applies_comment_translation_after_structure(self):
        orch = _make_orchestrator(dry_run=False)
        script = _make_script()
        content = _make_content()
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


class TestStepCommentTranslations:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        script = _make_script()
        out_c, out_s = orch._apply_comment_translations(content, script, "2026-04-26")
        assert out_c is content
        assert out_s is script

    def test_no_script_skips(self):
        orch = _make_orchestrator(dry_run=False)
        orch.translation_manager = MagicMock()
        content = _make_content()
        out_c, out_s = orch._apply_comment_translations(content, None, "2026-04-26")
        assert out_c is content
        assert out_s is None
        orch.translation_manager.translate.assert_not_called()


class TestStepSynthesizeAudio:
    def test_dry_run_returns_script_with_zero_audio(self):
        orch = _make_orchestrator(dry_run=True)
        script = _make_script()
        result = orch._step_synthesize_audio(_make_content(), script, "2026-04-26")
        assert result is script
        assert all(s.audio_path == "" for s in result.segments)

    def test_no_script_returns_none(self):
        orch = _make_orchestrator(dry_run=False)
        orch.tts_processor = MagicMock()
        result = orch._step_synthesize_audio(_make_content(), None, "2026-04-26")
        assert result is None
        orch.tts_processor.process_audio.assert_not_called()


class TestStepTitle:
    def test_dry_run_returns_script_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        script = _make_script()
        result = orch._step_title(_make_content(), script, "2026-04-26")
        assert result is script

    def test_no_script_returns_none(self):
        orch = _make_orchestrator(dry_run=False)
        result = orch._step_title(_make_content(), None, "2026-04-26")
        assert result is None

    def test_title_caches_cover_variants_for_downstream_cover_step(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        content = ContentPackage(
            date=date,
            items=[
                ContentItem(
                    source="hackernews",
                    source_id="1",
                    title="A story",
                    url="https://example.com/story",
                    title_cn="一个故事",
                    editor_angle="影响开发者",
                )
            ],
        )
        orch = _make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock(
            return_value={
                "title": "【HN日报】一个故事：影响开发者",
                "description": "简介",
                "title_candidates": ["主推", "备选一", "备选二"],
                "cover_title": "一个故事\n影响开发者",
                "cover_subtitle": "— 对象\n— 代价\n— 人群",
                "cover_tags": ["开发者"],
                "cover_highlights": ["影响"],
                "cover_prompt": "Asymmetric 16:9 editorial illustration of a technology conflict on the right, clean negative space on the left.",
                "cover_variants": [
                    {
                        "angle": "争议·支持方",
                        "cover_title": "一个故事\n方向仍需验证",
                        "cover_subtitle": "— 对象\n— 进展\n— 长期投入",
                        "cover_tags": ["支持角度"],
                        "cover_highlights": ["验证"],
                    },
                    {
                        "angle": "争议·反对方",
                        "cover_title": "一个故事\n风险暴露",
                        "cover_subtitle": "— 对象\n— 成本\n— 受影响人群",
                        "cover_tags": ["风险角度"],
                        "cover_highlights": ["风险"],
                    },
                    {
                        "angle": "争议·中立方",
                        "cover_title": "一个故事\n争议未解",
                        "cover_subtitle": "— 对象\n— 分歧\n— 待验证结果",
                        "cover_tags": ["观察角度"],
                        "cover_highlights": ["争议"],
                    },
                ],
                "tags": ["AI"],
            }
        )
        orch.llm_provider.fast_model = "test-fast"
        orch.llm_provider.fast_temperature = 0.1

        orch._step_title(content, _make_script(), date)

        title_payload = json.loads(
            (tmp_path / "data" / "2026-04" / date / "publish" / "title.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(title_payload["cover_variants"]) == 3
        assert title_payload["cover_variants"][1]["title"] == "一个故事\n风险暴露"
        assert title_payload["cover_prompt"].endswith("no footer bars.")
        assert orch.llm_provider.complete_prompt.call_count == 1


class TestStepCoverImage:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_cover_image(_make_content(), _make_script(), "2026-04-26")
        assert result is None
        orch.image_generator = None

    def test_uses_title_cached_variants_without_cover_variants_llm_call(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        render_dir = tmp_path / "data" / "2026-04" / date / "render"
        render_dir.mkdir(parents=True)
        (render_dir / "cover_bg.png").write_bytes(b"png")
        title_path = tmp_path / "data" / "2026-04" / date / "publish" / "title.json"
        title_path.parent.mkdir(parents=True)
        title_path.write_text(
            json.dumps(
                {
                    "cover_variants": [
                        {
                            "cover_title": "主体\n支持角度",
                            "cover_subtitle": "— 对象\n— 进展\n— 长期投入",
                            "cover_tags": ["支持"],
                            "cover_highlights": ["支持"],
                        },
                        {
                            "cover_title": "主体\n风险角度",
                            "cover_subtitle": "— 对象\n— 成本\n— 受影响人群",
                            "cover_tags": ["风险"],
                            "cover_highlights": ["风险"],
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        orch = _make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock()

        orch._step_cover_image(_make_content(), _make_script(), date)

        orch.llm_provider.complete_prompt.assert_not_called()
        props = json.loads(
            (render_dir / "cover_props_v2.json").read_text(encoding="utf-8")
        )
        assert props["title"] == "主体\n风险角度"

        title_payload = json.loads(title_path.read_text(encoding="utf-8"))
        title_payload["cover_variants"][1]["cover_title"] = "主体\n更新后的风险"
        title_path.write_text(
            json.dumps(title_payload, ensure_ascii=False), encoding="utf-8"
        )
        orch._step_cover_image(_make_content(), _make_script(), date)

        refreshed = json.loads(
            (render_dir / "cover_props_v2.json").read_text(encoding="utf-8")
        )
        assert refreshed["title"] == "主体\n更新后的风险"
        orch.llm_provider.complete_prompt.assert_not_called()

    def test_uses_title_cached_visual_prompt_without_cover_prompt_llm_call(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        title_path = tmp_path / "data" / "2026-04" / date / "publish" / "title.json"
        title_path.parent.mkdir(parents=True)
        title_path.write_text(
            json.dumps(
                {"cover_prompt": "cached visual prompt for today's conflict"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        prompts = []
        image_generator = MagicMock()

        def generate(prompt, output_path, **kwargs):
            prompts.append(prompt)
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"png")

        image_generator.generate.side_effect = generate
        orch = _make_orchestrator(dry_run=False)
        orch.image_generator = image_generator
        orch.config["image_generator"] = {"candidate_count": 1}
        orch.llm_provider.complete_prompt = MagicMock()

        orch._step_cover_image(_make_content(), _make_script(), date)

        assert len(prompts) == 1
        assert prompts[0].startswith("cached visual prompt")
        assert "No logos" in prompts[0]
        orch.llm_provider.complete_prompt.assert_not_called()

        title_path.write_text(
            json.dumps(
                {"cover_prompt": "updated visual prompt for the same conflict"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        orch._step_cover_image(_make_content(), _make_script(), date)

        assert len(prompts) == 2
        assert prompts[1].startswith("updated visual prompt")
        orch.llm_provider.complete_prompt.assert_not_called()


class TestStepCoverThumbnail:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        with patch.object(Path, "exists", return_value=True):
            result = orch._step_cover_thumbnail(
                _make_content(), _make_script(), "2026-04-26"
            )
        assert result is None


class TestWritePublishGuide:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._write_publish_guide(
            _make_content(), _make_script(), "2026-04-26"
        )
        assert result is None

    def test_regenerates_when_manifest_input_hash_is_missing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        base = tmp_path / "data" / date[:7] / date / "publish"
        base.mkdir(parents=True)
        guide_path = base / "publish_guide.md"
        guide_path.write_text("old", encoding="utf-8")

        orch = _make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock()
        orch.llm_provider.complete_prompt.return_value = "new guide"
        orch.llm_provider.fast_model = "test-fast"
        orch.llm_provider.fast_temperature = 0.1

        orch._write_publish_guide(_make_content(), _make_script(), date)

        assert guide_path.read_text(encoding="utf-8") == "new guide"
        orch.llm_provider.complete_prompt.assert_called_once()

    def test_uses_title_json_for_publish_metadata_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        base = tmp_path / "data" / date[:7] / date / "publish"
        base.mkdir(parents=True)
        (base / "title.json").write_text(
            json.dumps(
                {
                    "title": "Published Title",
                    "description": "Published description",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        orch = _make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock(return_value="guide")
        orch.llm_provider.fast_model = "test-fast"
        orch.llm_provider.fast_temperature = 0.1

        orch._write_publish_guide(_make_content(), _make_script(), date)

        context = orch.llm_provider.complete_prompt.call_args.args[1]
        assert context["script_title"] == "Published Title"
        assert context["script_description"] == "Published description"
        assert "prompt_hash" not in context


class TestStepPrepareRender:
    def test_dry_run_does_not_call_renderer(self):
        orch = _make_orchestrator(dry_run=True)
        orch._step_prepare_render(_make_content(), _make_script(), "2026-04-26")
        orch.renderer.write_props.assert_not_called()

    def test_no_script_raises(self):
        orch = _make_orchestrator(dry_run=False)
        with pytest.raises(ValueError, match="Script not loaded"):
            orch._step_prepare_render(_make_content(), None, "2026-04-26")
        orch.renderer.write_props.assert_not_called()

    def test_invokes_renderer_write_props(self, tmp_path):
        orch = _make_orchestrator(dry_run=False)
        script = _make_script()
        content = _make_content()
        orch._write_publish_guide = MagicMock()
        # write_props contract: returns (props_path, props_json, scenes_payload).
        # The mock would otherwise return a bare MagicMock, which can't be
        # unpacked into 3 values.
        props_path = tmp_path / "props.json"
        props_path.write_text("{}", encoding="utf-8")
        orch.renderer.write_props.return_value = (props_path, "{}", {})
        orch._step_prepare_render(content, script, "2026-04-26")
        orch.renderer.write_props.assert_called_once()
        orch._write_publish_guide.assert_called_once_with(content, script, "2026-04-26")


class TestStepRender:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_render(_make_script(), "2026-04-26")
        assert result is None
        orch.renderer.render.assert_not_called()


# ── run() dispatch ──────────────────────────────────────────────────────


class TestRunDispatch:
    def test_runs_only_requested_step_chain(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=True)
        # Patch all _step_* methods to detect which get called
        step_names = [
            "_step_fetch",
            "_step_prefilter",
            "_step_fetch_comments",
            "_step_enrich_articles",
            "_step_judge_comments",
            "_step_write_script",
            "_step_prepare_subtitles",
            "_step_synthesize_audio",
            "_step_title",
            "_step_cover_image",
            "_step_cover_thumbnail",
            "_step_prepare_render",
        ]
        mocks = {}
        for name in step_names:
            m = MagicMock()
            if name == "_step_enrich_articles":
                m.return_value = (_make_content(), [])
            elif name in (
                "_step_synthesize_audio",
                "_step_title",
                "_step_write_script",
            ):
                m.return_value = _make_script()
            elif name == "_step_fetch":
                m.return_value = _make_content()
            else:
                m.return_value = None
            setattr(orch, name, m)
            mocks[name] = m

        # Request only "title" — do not replay the full editorial chain.
        # A missing content artifact may still trigger the fetch fallback, and
        # protected production output always passes through human review.
        orch.run("2026-04-26", steps=["title"], force=False)

        # Only the requested step, its data fallback, and the review gate run.
        steps_in_order = [
            "_step_fetch",
            "_step_title",
        ]
        steps_after = [
            "_step_synthesize_audio",
            "_step_cover_image",
            "_step_cover_thumbnail",
            "_step_prepare_render",
        ]
        for name in steps_in_order:
            mocks[name].assert_called_once(), f"{name} should have been called"
        for name in steps_after:
            mocks[name].assert_not_called(), f"{name} should NOT have been called"

    def test_agent_mode_dry_run_does_not_write_state_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=True)
        orch.agent_mode = True

        orch.run("2026-04-26", steps=["fetch"], force=False)

        workflow_path = (
            tmp_path
            / "data"
            / "2026-04"
            / "2026-04-26"
            / "agent"
            / "workflow_video.json"
        )
        assert not workflow_path.exists()

    def test_video_downstream_run_writes_runtime_artifacts_without_upstream_steps(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        orch._write_publish_guide = MagicMock()

        content = _make_content()
        script = _make_script()
        orch.content_preparer.save_content(content, date)
        save_script(script, date)
        generate_script_review_page(script, date)
        approve_current_script(date, reviewer="test")
        workflow = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
        workflow.ensure()
        for state_name in ("ingest", "research", "editorial", "human_review"):
            workflow.mark_running(state_name)
            workflow.mark_done(state_name)

        def synthesize(current_script, _date, _content):
            audio_path = (
                tmp_path
                / "data"
                / date[:7]
                / date
                / "pipeline"
                / "audio"
                / "segment_00.mp3"
            )
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"audio")
            segment = current_script.segments[0]
            segment.actual_duration = 1.0
            segment.start_time = 0.0
            segment.end_time = 1.0
            segment.audio_path = str(audio_path)
            return current_script

        orch.tts_processor.process_audio = MagicMock(side_effect=synthesize)
        props_path = tmp_path / "data" / date[:7] / date / "render" / "cli_props.json"

        def write_props(_script, _audio_dir, _content, **kwargs):
            props_path.parent.mkdir(parents=True, exist_ok=True)
            props_path.write_text("{}", encoding="utf-8")
            return props_path, "{}", {}

        orch.renderer.write_props.side_effect = write_props

        def render(_script, _audio_dir, output_path, _content, date=None):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"video")

        orch.renderer.render.side_effect = render

        orch.run(
            date,
            steps=["synthesize_audio", "prepare_render", "render"],
            force=False,
        )

        orch.content_fetcher.fetch.assert_not_called()
        orch.tts_processor.process_audio.assert_called_once()
        orch.renderer.write_props.assert_called_once()
        orch.renderer.render.assert_called_once()
        assert Path(f"data/{date[:7]}/{date}/pipeline/audio_manifest.json").exists()
        assert Path(f"data/{date[:7]}/{date}/pipeline/subtitle_plan.json").exists()
        assert Path(f"data/{date[:7]}/{date}/agent/script_lock.json").exists()
        assert Path(f"data/{date[:7]}/{date}/publish/output.mp4.manifest.json").exists()
        persisted_script = json.loads(
            Path(f"data/{date[:7]}/{date}/pipeline/script.json").read_text(
                encoding="utf-8"
            )
        )
        assert persisted_script["segments"][0]["audio_text"] == "hi"
        workflow_state = json.loads(
            Path(f"data/{date[:7]}/{date}/agent/workflow_video.json").read_text(
                encoding="utf-8"
            )
        )
        assert workflow_state["metadata"]["execution_mode"] == "native_orchestrator"
        assert workflow_state["metadata"]["execution_status"] == "complete"
        assert workflow_state["states"]["produce"]["status"] == "done"

    def test_agent_mode_scopes_non_render_step_state_to_video(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        content = _make_content()
        orch._step_fetch = MagicMock(return_value=content)

        orch.run("2026-04-26", steps=["fetch"], force=False)

        assert Path("data/2026-04/2026-04-26/agent/workflow_video.json").exists()

    def test_agent_mode_blocks_after_enrichment_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        content = _make_failed_content_with_comments()
        script = _make_script()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch._step_judge_comments = MagicMock(return_value=content)
        orch._step_write_script = MagicMock(return_value=script)

        orch.run(
            "2026-04-26",
            steps=["enrich_articles", "write_script"],
            force=False,
        )

        orch._step_write_script.assert_not_called()
        workflow_state = json.loads(
            Path("data/2026-04/2026-04-26/agent/workflow_video.json").read_text(
                encoding="utf-8"
            )
        )
        assert workflow_state["states"]["research"]["status"] == "blocked"
        assert (
            workflow_state["metadata"]["blocked_reason"] == "manual_download_required"
        )
        assert workflow_state["metadata"]["blocked_items"][0]["story_id"] == "123"
        task_path = (
            tmp_path / "data" / "2026-04" / "2026-04-26" / "agent" / "agent_tasks.json"
        )
        tasks = json.loads(task_path.read_text(encoding="utf-8"))
        assert tasks["schema_version"] == 2
        assert tasks["repair_contract"]["owner"] == "agent"
        assert (
            "reliable HTML or PDF source"
            in tasks["repair_contract"]["minimum_success_condition"]
        )
        assert tasks["tasks"][0]["task_type"] == "fetch_article"
        assert tasks["tasks"][0]["save_as"]["html"].endswith("123.html")
        assert tasks["tasks"][0]["acceptable_outputs"] == [
            "html",
            "pdf",
            "synthesis_html",
        ]
        assert any(
            line.endswith("scripts/agent_run.py --date 2026-04-26 --resume")
            for line in tasks["tasks"][0]["repair_steps"]
        )
        assert "Do not fabricate" in tasks["tasks"][0]["failure_policy"]
        events_path = (
            tmp_path
            / "data"
            / "2026-04"
            / "2026-04-26"
            / "agent"
            / "agent_events.jsonl"
        )
        assert "run_blocked" in events_path.read_text(encoding="utf-8")
        assert workflow_state["metadata"]["agent_task_file"].endswith(
            "agent_tasks.json"
        )

    def test_agent_mode_can_allow_degraded_enrichment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        orch.allow_degraded_enrichment = True
        content = _make_failed_content()
        script = _make_script()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch._step_judge_comments = MagicMock(return_value=content)
        orch._step_write_script = MagicMock(return_value=script)

        orch.run(
            "2026-04-26",
            steps=["enrich_articles", "write_script"],
            force=False,
        )

        orch._step_write_script.assert_called_once()
        workflow_state = json.loads(
            Path("data/2026-04/2026-04-26/agent/workflow_video.json").read_text(
                encoding="utf-8"
            )
        )
        assert workflow_state["metadata"]["execution_status"] == "complete"
        assert workflow_state["metadata"]["degraded_items"][0]["story_id"] == "123"
        assert workflow_state["metadata"]["degraded_items"][0]["continued"] is True

    def test_refresh_variants_clears_script_outputs_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        base = tmp_path / "data" / "2026-04" / "2026-04-26"
        segments = base / "pipeline" / "segments"
        variants = base / "pipeline" / "variants"
        segments.mkdir(parents=True)
        variants.mkdir(parents=True)
        (base / "pipeline" / "content.json").write_text("{}", encoding="utf-8")
        (base / "pipeline" / "script.json").write_text("{}", encoding="utf-8")
        (variants / "index.json").write_text("{}", encoding="utf-8")
        (segments / "story_scan_item_0.json").write_text("{}", encoding="utf-8")
        (segments / "translation_titles.json").write_text("{}", encoding="utf-8")
        orch = _make_orchestrator(dry_run=False)

        orch._refresh_variant_outputs("2026-04-26")

        assert (base / "pipeline" / "content.json").exists()
        assert not (base / "pipeline" / "script.json").exists()
        assert not variants.exists()
        assert not (segments / "story_scan_item_0.json").exists()
        assert (segments / "translation_titles.json").exists()

    def test_agent_mode_blocks_insufficient_story_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        content = _make_failed_content()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch.run(
            "2026-04-26",
            steps=["enrich_articles"],
            force=False,
        )

        workflow_state = json.loads(
            Path("data/2026-04/2026-04-26/agent/workflow_video.json").read_text(
                encoding="utf-8"
            )
        )
        assert workflow_state["states"]["research"]["status"] == "blocked"
        assert (
            workflow_state["metadata"]["blocked_reason"] == "insufficient_story_context"
        )
        assert workflow_state["metadata"]["blocked_items"][0]["comment_count"] == 0
