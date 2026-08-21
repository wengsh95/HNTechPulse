import json
from pathlib import Path
from unittest.mock import MagicMock

from src.core.models import ContentItem, ContentPackage
from src.pipeline.stages.title_cover import (
    _clean_publish_description,
    _downgrade_unsupported_publish_claims,
    _ensure_all_stories_in_description,
    _normalize_cover_prompt,
    _normalize_cover_variants,
)
from tests.stage_fixtures import make_content, make_orchestrator, make_script


class TestTitleCoverHelpers:
    def test_clean_description_removes_discussion_cliche_and_bounds_copy(self):
        text = "这是第一句。欢迎在评论区聊聊。" + "补充说明。" * 80

        result = _clean_publish_description(text, max_len=24)

        assert "评论区" not in result
        assert len(result) <= 24

    def test_downgrade_publish_claims_avoids_unsupported_certainty(self):
        result = _downgrade_unsupported_publish_claims("系统掉线，平台砍掉P2P")

        assert "掉线" not in result
        assert "砍掉P2P" not in result
        assert "延迟升高" in result

    def test_normalize_cover_variants_filters_and_caps_entries(self):
        raw = [
            {"cover_title": "主体", "cover_tags": ["A", "B", "C"]},
            {"cover_title": ""},
            {"cover_title": "第二个"},
            {"cover_title": "第三个"},
            {"cover_title": "第四个"},
        ]

        result = _normalize_cover_variants(raw)

        assert [item["title"] for item in result] == ["主体", "第二个", "第三个"]
        assert result[0]["tags"] == ["A", "B"]

    def test_normalize_cover_prompt_adds_safety_suffix_and_truncates(self):
        result = _normalize_cover_prompt("prompt " * 400)

        assert len(result) <= 1200 + len(
            ", No logos, no text, no watermarks, no brand references, no horizontal bars, no vertical bars, no UI elements, no header bars, no footer bars."
        )
        assert "No logos" in result

    def test_ensure_all_stories_in_description_appends_missing_story(self):
        focus = {"title_cn": "焦点故事", "editor_angle": "焦点影响"}
        other = [{"title_cn": "另一个故事", "editor_angle": "另一个影响"}]

        result = _ensure_all_stories_in_description("焦点故事。", focus, other)

        assert "另一个影响" in result


class TestTitleStage:
    def test_dry_run_returns_script_unchanged(self):
        orch = make_orchestrator(dry_run=True)
        script = make_script()

        assert orch._step_title(make_content(), script, "2026-04-26") is script

    def test_no_script_returns_none(self):
        orch = make_orchestrator(dry_run=False)

        assert orch._step_title(make_content(), None, "2026-04-26") is None

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
        orch = make_orchestrator(dry_run=False)
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
                        "cover_title": "一个故事\n方向仍需验证",
                        "cover_tags": ["支持角度"],
                    },
                    {"cover_title": "一个故事\n风险暴露", "cover_tags": ["风险角度"]},
                    {"cover_title": "一个故事\n争议未解", "cover_tags": ["观察角度"]},
                ],
                "tags": ["AI"],
            }
        )

        orch._step_title(content, make_script(), date)

        title_payload = json.loads(
            (tmp_path / "data" / "2026-04" / date / "publish" / "title.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(title_payload["cover_variants"]) == 3
        assert title_payload["cover_variants"][1]["title"] == "一个故事\n风险暴露"
        assert title_payload["cover_prompt"].endswith("no footer bars.")


class TestCoverImageStage:
    def test_dry_run_returns_none(self):
        orch = make_orchestrator(dry_run=True)

        assert (
            orch._step_cover_image(make_content(), make_script(), "2026-04-26") is None
        )

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
                        {"cover_title": "主体\n支持角度", "cover_tags": ["支持"]},
                        {"cover_title": "主体\n风险角度", "cover_tags": ["风险"]},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        orch = make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock()

        orch._step_cover_image(make_content(), make_script(), date)

        assert orch.llm_provider.complete_prompt.call_count == 0
        props = json.loads(
            (render_dir / "cover_props_v2.json").read_text(encoding="utf-8")
        )
        assert props["title"] == "主体\n风险角度"

    def test_uses_title_cached_visual_prompt_without_cover_prompt_llm_call(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        title_path = tmp_path / "data" / "2026-04" / date / "publish" / "title.json"
        title_path.parent.mkdir(parents=True)
        title_path.write_text(
            json.dumps({"cover_prompt": "cached visual prompt for today's conflict"}),
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
        orch = make_orchestrator(dry_run=False)
        orch.image_generator = image_generator
        orch.config["image_generator"] = {"candidate_count": 1}
        orch.llm_provider.complete_prompt = MagicMock()

        orch._step_cover_image(make_content(), make_script(), date)

        assert len(prompts) == 1
        assert prompts[0].startswith("cached visual prompt")
        assert "No logos" in prompts[0]
        assert orch.llm_provider.complete_prompt.call_count == 0
