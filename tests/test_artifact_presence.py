"""Typed artifact-presence facts shared by the progress summary and the audit."""

import json
from pathlib import Path

from src.pipeline.pipeline_progress import PipelineProgress
from src.workflow import ArtifactPresence, presence_for_step, publish_presence

DATE = "2030-01-02"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _presence_by_name(date: str = DATE) -> dict[str, ArtifactPresence]:
    return {presence.name: presence for presence in presence_for_step(date)}


class TestPresenceForStepNoContent:
    def test_returns_all_chain_steps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        presences = presence_for_step(DATE)
        names = [p.name for p in presences]
        assert names == [
            "fetch",
            "prefilter",
            "fetch_comments",
            "enrich_articles",
            "judge_comments",
            "write_script",
            "synthesize_audio",
            "title",
            "cover_image",
            "cover_thumbnail",
            "draft_storyboard",
            "apply_storyboard",
            "prepare_render",
        ]

    def test_content_mutating_steps_say_fetch_first(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        by_name = _presence_by_name()
        assert by_name["fetch"].ready is False
        assert by_name["fetch"].detail == "will fetch"
        assert by_name["prefilter"].ready is False
        assert by_name["prefilter"].detail == "fetch first"
        assert by_name["fetch_comments"].detail == "fetch first"
        assert by_name["enrich_articles"].detail == "fetch first"

    def test_download_steps_judged_from_own_artifacts(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        by_name = _presence_by_name()
        # judge_comments / write_script are unconditional (artifact-backed)
        assert by_name["judge_comments"].detail == "will generate comment judgement"
        assert by_name["write_script"].detail == "will generate script"
        assert by_name["synthesize_audio"].detail == "will synthesize"
        assert by_name["title"].detail == "will generate title"
        assert by_name["apply_storyboard"].detail == (
            "no storyboard; keep generated templates"
        )
        assert by_name["prepare_render"].detail == (
            "will write props.json + publish guide"
        )


class TestPresenceWithContent:
    def test_fetch_reports_item_count(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(
            pipeline_path(DATE, "content.json"), {"items": [{"a": 1}, {"b": 2}]}
        )
        by_name = _presence_by_name()
        assert by_name["fetch"].ready is True
        assert by_name["fetch"].detail == "2 items cached"

    def test_fetch_comments_ready_when_all_have_counts(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(
            pipeline_path(DATE, "content.json"),
            {"items": [{"comment_count": 3}, {"comment_count": 1}]},
        )
        by_name = _presence_by_name()
        assert by_name["fetch_comments"].ready is True
        assert by_name["fetch_comments"].detail == "comments attached"

    def test_fetch_comments_not_ready_when_zero_counts(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(
            pipeline_path(DATE, "content.json"),
            {"items": [{"comment_count": 0}, {"comment_count": 1}]},
        )
        by_name = _presence_by_name()
        assert by_name["fetch_comments"].ready is False
        assert by_name["fetch_comments"].detail == "will fetch comments"

    def test_enrich_ready_when_no_pending(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(
            pipeline_path(DATE, "content.json"),
            {"items": [{"enrichment_source": "enriched"}]},
        )
        by_name = _presence_by_name()
        assert by_name["enrich_articles"].ready is True
        assert by_name["enrich_articles"].detail == "articles enriched"

    def test_enrich_reports_pending_count(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(
            pipeline_path(DATE, "content.json"),
            {
                "items": [
                    {"enrichment_source": "enriched"},
                    {"enrichment_source": "fetch_failed"},
                ]
            },
        )
        by_name = _presence_by_name()
        assert by_name["enrich_articles"].ready is False
        assert by_name["enrich_articles"].detail == "1/2 need enrichment"

    def test_prefilter_ready_when_file_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        _write_json(pipeline_path(DATE, "content.json"), {"items": []})
        prefilter_path = pipeline_path(DATE, "prefilter.json")
        prefilter_path.parent.mkdir(parents=True, exist_ok=True)
        prefilter_path.write_text("{}", encoding="utf-8")
        by_name = _presence_by_name()
        assert by_name["prefilter"].ready is True
        assert by_name["prefilter"].detail == "prefilter cached"

    def test_unreadable_content_treated_as_fetch_first(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import pipeline_path

        content_path = pipeline_path(DATE, "content.json")
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_text("{not json", encoding="utf-8")
        by_name = _presence_by_name()
        assert by_name["fetch"].ready is False
        assert by_name["prefilter"].detail == "fetch first"


class TestPublishPresence:
    def test_all_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        presences = publish_presence(DATE)
        assert [p.name for p in presences] == ["title", "cover", "publish_guide"]
        assert all(p.ready is False for p in presences)

    def test_tracks_existing_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import publish_path

        title_path = publish_path(DATE, "title.json")
        title_path.parent.mkdir(parents=True, exist_ok=True)
        title_path.write_text("{}", encoding="utf-8")
        presences = publish_presence(DATE)
        by_name = {p.name: p for p in presences}
        assert by_name["title"].ready is True
        assert by_name["cover"].ready is False
        assert by_name["publish_guide"].ready is False

    def test_cover_refers_to_cover_png(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import publish_path

        cover_path = publish_path(DATE, "cover.png")
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cover_path.write_text("png", encoding="utf-8")
        presences = publish_presence(DATE)
        by_name = {p.name: p for p in presences}
        assert by_name["cover"].ready is True
        assert by_name["cover"].path == cover_path


class TestProgressIntegration:
    def test_check_cache_mirrors_presence_table(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = {"llm": {"model": "m"}, "pipeline": {"target_story_count": 3}}
        progress = PipelineProgress(["fetch", "prefilter"], DATE, config)
        triples = progress._check_cache()
        assert triples == [
            (presence.name, "✓" if presence.ready else "-", presence.detail)
            for presence in presence_for_step(DATE)
        ]

    def test_summary_includes_only_requested_steps(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = {"llm": {"model": "m"}, "pipeline": {"target_story_count": 3}}
        progress = PipelineProgress(["fetch", "title"], DATE, config)
        lines = progress._build_summary(force=False)
        joined = "\n".join(lines)
        assert f"  - {'fetch':12s} will fetch" in joined
        assert f"  - {'title':12s} will generate title" in joined
        assert "write_script" not in joined
        assert "Pipeline Execution Summary" in joined

    def test_ready_steps_show_check_mark(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from src.pipeline.paths import publish_path

        title_path = publish_path(DATE, "title.json")
        title_path.parent.mkdir(parents=True, exist_ok=True)
        title_path.write_text("{}", encoding="utf-8")
        config = {"llm": {"model": "m"}, "pipeline": {"target_story_count": 3}}
        progress = PipelineProgress(["title"], DATE, config)
        lines = progress._build_summary(force=False)
        assert f"  ✓ {'title':12s} title cached" in "\n".join(lines)
