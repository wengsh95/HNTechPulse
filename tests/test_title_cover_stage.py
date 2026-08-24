import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.models import ContentItem, ContentPackage
from src.pipeline.stages.title_cover import (
    _clean_publish_description,
    _downgrade_unsupported_publish_claims,
    _ensure_all_stories_in_description,
    _normalize_cover_prompt,
    _normalize_cover_variants,
    _preserve_source_uncertainty,
    _publish_title_width,
    _validate_title_grounding,
    _validate_title_payload,
    _validate_cover_title_shape,
)
from tests.stage_fixtures import make_content, make_orchestrator, make_script


class TestTitleCoverHelpers:
    def test_clean_description_removes_discussion_cliche_and_bounds_copy(self):
        text = "这是第一句。欢迎在评论区聊聊。" + "补充说明。" * 80

        result = _clean_publish_description(text, max_len=24)

        assert "评论区" not in result
        assert len(result) <= 24

    def test_clean_description_removes_exact_duplicate_sentences(self):
        assert _clean_publish_description("同一个事实。同一个事实。") == "同一个事实。"

    def test_downgrade_publish_claims_avoids_unsupported_certainty(self):
        result = _downgrade_unsupported_publish_claims("系统掉线，平台砍掉P2P")

        assert "掉线" not in result
        assert "砍掉P2P" not in result
        assert "延迟升高" in result
        assert "疑似" in _downgrade_unsupported_publish_claims("偷偷降档")
        assert _downgrade_unsupported_publish_claims("疑似暗降") == "疑似降"
        assert "信任风险" in _downgrade_unsupported_publish_claims("信任崩塌")
        assert "疑似收到低档输出" in _downgrade_unsupported_publish_claims(
            "付费用户被疑似削弱"
        )
        assert (
            _downgrade_unsupported_publish_claims("付费用户能不能被暗中削弱")
            == "付费用户是否收到低档输出"
        )
        assert (
            _downgrade_unsupported_publish_claims("Anthropic悄悄\n偷偷给Claude降档")
            == "Anthropic\n疑似给Claude降档"
        )
        assert (
            _downgrade_unsupported_publish_claims("Claude被指服务器端疑似降档")
            == "Claude被指服务器端降档"
        )
        assert (
            _downgrade_unsupported_publish_claims("付费用户被疑似A/B，知情权失守")
            == "付费用户疑似被纳入A/B，知情权争议"
        )
        assert (
            _downgrade_unsupported_publish_claims("Anthropic疑似\n付费信任失守")
            == "Anthropic被指\n计费引发质疑"
        )
        assert (
            _downgrade_unsupported_publish_claims("Claude Code\n降档高价计费引发争议")
            == "Claude Code\n降档计费争议"
        )

    def test_publish_title_width_excludes_prefix_and_counts_cjk_as_two(self):
        assert _publish_title_width("【HN日报】Claude降档") == 10

    def test_cover_title_shape_rejects_line_that_would_wrap(self):
        with pytest.raises(ValueError, match="line visual width"):
            _validate_cover_title_shape(
                "Claude Code\n付费用户疑似被纳入测试", label="cover"
            )

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

    def test_normalize_cover_variants_round_trips_canonical_title_json(self):
        canonical = [
            {
                "title": "支持角度",
                "subtitle": "副标题",
                "tags": ["支持"],
                "highlights": ["角度"],
            },
            {"title": "风险角度", "tags": ["风险"]},
        ]

        assert _normalize_cover_variants(canonical) == [
            canonical[0],
            {
                "title": "风险角度",
                "subtitle": "",
                "tags": ["风险"],
                "highlights": [],
            },
        ]

    def test_normalize_cover_prompt_adds_safety_suffix_and_truncates(self):
        result = _normalize_cover_prompt("prompt " * 400)

        assert len(result) <= 1200 + len(
            ", No logos, no text, no watermarks, no brand references, no horizontal bars, no vertical bars, no UI elements, no header bars, no footer bars."
        )
        assert "No logos" in result

    def test_normalize_cover_prompt_does_not_duplicate_suffix_without_period(self):
        raw = (
            "Visual metaphor, No logos, no text, no watermarks, no brand references, "
            "no horizontal bars, no vertical bars, no UI elements, no header bars, "
            "no footer bars"
        )

        assert _normalize_cover_prompt(raw).lower().count("no logos") == 1

    def test_title_payload_requires_three_distinct_cover_variants(self):
        with pytest.raises(ValueError, match="three distinct"):
            _validate_title_payload(
                {
                    "title": "这是一个足够长的发布标题",
                    "description": "描述",
                    "cover_variants": [
                        {"cover_title": "重复"},
                        {"cover_title": "重复"},
                        {"cover_title": "重复"},
                    ],
                }
            )

    def test_title_payload_requires_subject_in_every_cover_variant(self):
        payload = {
            "title": "【HN日报】Claude被曝降档：计费争议",
            "title_candidates": [
                "【HN日报】Claude被曝降档：计费争议",
                "【HN日报】Claude疑似降档：用户反馈",
                "【HN日报】Claude降档争议：仍待验证",
            ],
            "description": "描述",
            "cover_title": "Claude\n疑似降档",
            "cover_variants": [
                {"cover_title": "Claude\n疑似降档"},
                {"cover_title": "付费用户\n计费争议"},
                {"cover_title": "Claude\n争议待验证"},
            ],
        }

        with pytest.raises(ValueError, match="company or product"):
            _validate_title_payload(payload)

    def test_title_payload_rejects_candidate_over_visual_width_limit(self):
        payload = {
            "title": "【HN日报】Claude被曝降档：计费争议",
            "title_candidates": [
                "【HN日报】Claude被曝降档：计费争议",
                "【HN日报】" + "过长" * 13,
                "【HN日报】Claude疑似降档：用户反馈",
            ],
            "description": "描述",
            "cover_title": "Claude\n疑似降档",
            "cover_variants": [
                {"cover_title": "Claude\n疑似降档"},
                {"cover_title": "Claude\n计费争议"},
                {"cover_title": "Claude\n争议待验证"},
            ],
        }

        with pytest.raises(ValueError, match="visual width"):
            _validate_title_payload(payload)

    def test_uncertain_source_requires_marker_on_cover_variants(self):
        payload = {
            "title": "【HN日报】Claude被曝降档：计费争议",
            "title_candidates": ["【HN日报】Claude被曝降档：计费争议"],
            "cover_title": "Claude\n疑似降档",
            "cover_variants": [
                {"cover_title": "Claude\n疑似降档"},
                {"cover_title": "Claude\n低档输出"},
            ],
        }

        with pytest.raises(ValueError, match="cover_variant"):
            _validate_title_grounding(
                payload, {"title": "Service appears to lower effort"}
            )

    def test_uncertain_source_requires_uncertainty_in_every_publish_title(self):
        payload = {
            "title": "【HN日报】平台降低档位：付费用户多花钱",
            "title_candidates": ["【HN日报】疑似降档：计费争议"],
            "cover_title": "疑似降档",
        }

        with pytest.raises(ValueError, match="this title"):
            _validate_title_grounding(
                payload, {"title": "Service appears to lower effort"}
            )

        assert _preserve_source_uncertainty(
            "【HN日报】平台降低档位：付费争议",
            {"title": "Service appears to lower effort"},
        ).startswith("【HN日报】被曝")

    def test_ensure_all_stories_in_description_appends_missing_story(self):
        focus = {"title_cn": "焦点故事", "editor_angle": "焦点影响"}
        other = [{"title_cn": "另一个故事", "editor_angle": "另一个影响"}]

        result = _ensure_all_stories_in_description("焦点故事。", focus, other)

        assert "另一个影响" in result

    def test_ensure_all_stories_recognizes_existing_ascii_product_name(self):
        focus = {"title_cn": "焦点故事", "editor_angle": "焦点影响"}
        other = [
            {
                "title": "MCP roadmap",
                "title_cn": "MCP路线图",
                "editor_angle": "MCP公布优先方向",
            }
        ]

        result = _ensure_all_stories_in_description(
            "焦点故事。MCP协议公布路线图。", focus, other
        )

        assert result == "焦点故事。MCP协议公布路线图。"


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
                "title_candidates": [
                    "【HN日报】一个故事：影响开发者",
                    "备选一",
                    "备选二",
                ],
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
