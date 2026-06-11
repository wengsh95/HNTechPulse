from unittest.mock import MagicMock

from src.core.models import (
    ContentItem,
    ContentComment,
    ContentPackage,
    Script,
    ScriptSegment,
    SceneElement,
    SelectionResult,
)
from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.pipeline.content_io import ContentPreparer
from src.pipeline.script import ScriptWriter
from src.pipeline.orchestrator import Orchestrator
from src.pipeline.comment import save_comment_judgements


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {
            "target_story_count": 3,
        },
        "llm": {"model": "test-model"},
    }


def _make_content_package():
    items = []
    for i in range(9):
        comments = [
            ContentComment(author=f"user_{j}", content=f"comment {j}") for j in range(3)
        ]
        items.append(
            ContentItem(
                source="hackernews",
                source_id=str(100 + i),
                title=f"Story {i}",
                url=f"https://example.com/{i}",
                score=100 - i * 10,
                comment_count=3,
                published_at=1700000000 + i * 100,
                editor_angle=f"角度 {i}",
                why_it_matters=f"重要性 {i}",
                comments=comments,
            )
        )
    return ContentPackage(
        date="2026-04-26",
        items=items,
    )


def _make_selection_result():
    return SelectionResult(
        brief_items=[{"story_index": 0}],
        raw_json='{"brief_items": [{"story_index": 0}]}',
    )


def _make_script():
    return Script(
        title="Test Script",
        description="Test",
        tags=["test"],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="Hello",
                duration=10.0,
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="News",
                duration=10.0,
            ),
        ],
    )


class TestContentPreparer:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """Save a ContentPackage, load it back, verify all fields match."""
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        preparer = ContentPreparer(config, debug=True)
        content = _make_content_package()
        content.items[0].why_it_matters = "影响开发工作流"
        content.items[0].editorial_score = 12.0
        content.items[0].news_focus = 4
        content.items[0].newsworthiness = 4
        content.items[0].category = "ai_company"
        content.items[0].comments_partial = True
        date = "2026-04-26"

        preparer.save_content(content, date)
        loaded = preparer.load_content(date)

        assert loaded.date == content.date
        assert len(loaded.items) == len(content.items)
        for original, loaded_item in zip(content.items, loaded.items):
            assert loaded_item.source == original.source
            assert loaded_item.source_id == original.source_id
            assert loaded_item.title == original.title
            assert loaded_item.url == original.url
            assert loaded_item.score == original.score
            assert loaded_item.comment_count == original.comment_count
            assert loaded_item.editorial_score == original.editorial_score
            assert loaded_item.news_focus == original.news_focus
            assert loaded_item.newsworthiness == original.newsworthiness
            assert loaded_item.category == original.category
            assert loaded_item.comments_partial == original.comments_partial
            assert loaded_item.why_it_matters == original.why_it_matters
            assert len(loaded_item.comments) == len(original.comments)
            for orig_c, load_c in zip(original.comments, loaded_item.comments):
                assert load_c.author == orig_c.author
                assert load_c.content == orig_c.content


def _make_mock_story_segment(**kwargs):
    """Build a realistic story_scan_item segment for mock LLM calls."""
    story_index = kwargs.get("story_index", 0)
    return ScriptSegment(
        segment_type="story_scan_item",
        audio_text="test",
        duration=10.0,
        scene_elements=[
            SceneElement(
                element_type="event_card",
                start_time=0.0,
                end_time=5.0,
                props={"story_index": story_index},
            ),
        ],
    )


class TestScriptWriter:
    def test_balanced_selection_prefers_editorial_score_over_hn_score(self):
        writer = ScriptWriter(_make_config(), MagicMock(), debug=True)
        content = _make_content_package()
        for item in content.items:
            item.editorial_score = 0.0
        content.items[0].score = 999
        content.items[0].editorial_score = 1.0
        content.items[1].score = 10
        content.items[1].editorial_score = 10.0
        content.items[2].score = 9
        content.items[2].editorial_score = 9.0

        specs = writer._build_story_specs(content, strategy="balanced")

        assert [spec["story_index"] for spec in specs[:3]] == [1, 2, 0]

    def test_write_calls_llm_provider(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        mock_llm = MagicMock()
        mock_llm.generate_single_story_segment.side_effect = _make_mock_story_segment

        writer = ScriptWriter(config, mock_llm, debug=True)

        content = _make_content_package()
        for item in content.items:
            item.title_cn = f"故事 {item.source_id}"

        script = writer.write(content)

        assert (
            mock_llm.generate_single_story_segment.call_count
            == config["pipeline"]["target_story_count"]
        )
        assert len(script.segments) >= 2  # at least opening + closing

    def test_write_passes_comment_judgement_to_story_generation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        mock_llm = MagicMock()
        mock_llm.generate_single_story_segment.side_effect = _make_mock_story_segment
        content = _make_content_package()
        for item in content.items:
            item.title_cn = f"故事 {item.source_id}"
        content.items[0].comments = [
            ContentComment(
                author="u",
                content="I am skeptical because this creates a real operational tradeoff.",
                source_id="c1",
                quality_score=0.8,
            )
        ]
        save_comment_judgements(
            content.date,
            {
                content.items[0].source_id: {
                    "story_id": content.items[0].source_id,
                    "quote_candidates": [
                        {"comment_id": "c1", "quote_score": 0.9, "has_viewpoint": True}
                    ],
                }
            },
        )

        writer = ScriptWriter(config, mock_llm, debug=True)
        writer.write(content)

        first_call = mock_llm.generate_single_story_segment.call_args_list[0]
        assert (
            first_call.kwargs["comments_data"]["quote_candidates"][0]["comment_id"]
            == "c1"
        )

    def test_closing_card_omits_daily_signal_heading(self):
        writer = ScriptWriter(_make_config(), MagicMock(), debug=True)
        segment = writer._generate_fixed_closing(
            "2026-04-26",
            [
                {
                    "category": "AI",
                    "keywords": ["Agents", "Infra", "Agents"],
                    "title_translation": "AI 正从产品功能，变成开发工作流的底层能力。",
                    "why_it_matters": "AI 正在改变开发者的工作方式。",
                },
                {
                    "category": "Developer Tools",
                    "keywords": ["Open Source"],
                    "title_translation": "开源工具链持续进化。",
                    "why_it_matters": "开源生态正在重塑开发工具。",
                },
            ],
        )

        props = segment.scene_elements[0].props
        assert "signal_label" not in props
        assert props.get("signal") != "今日信号"
        assert props["keywords_label"] == "今日关键词"
        assert props["keywords"] == ["AI", "Agents", "Infra"]
        assert props["summary_label"] == "今日脉络"
        assert props["summary_items"][0]["category"] == "AI"
        assert (
            props["summary_items"][0]["title"]
            == "AI正从产品功能，变成开发工作流的底层能力。"
        )
        assert props["totals"]["story_count"] == 2


class TestOrchestrator:
    def test_dry_run_fetch(self):
        config = _make_config()
        mock_fetcher = MagicMock(spec=ContentFetcher)
        mock_llm = MagicMock(spec=LLMProvider)
        mock_tts = MagicMock(spec=TTSProvider)
        mock_renderer = MagicMock(spec=Renderer)

        orch = Orchestrator(
            config=config,
            content_fetcher=mock_fetcher,
            llm_provider=mock_llm,
            tts_provider=mock_tts,
            renderer=mock_renderer,
            debug=True,
            dry_run=True,
        )
        orch.run(date="2026-04-26", steps=["fetch"])
        mock_fetcher.fetch.assert_not_called()


class TestLLMProviderInterface:
    def test_selection_result_importable_from_core(self):
        from src.core.models import SelectionResult

        assert SelectionResult is not None

    def test_llm_provider_interface_references_core_types(self):
        import inspect

        sig = inspect.signature(LLMProvider.generate_single_story_segment)
        assert "content" in sig.parameters
        assert "story_index" in sig.parameters


class TestScriptTemplates:
    def test_opening_and_closing_are_bilibili_oriented(self):
        from src.pipeline.script.templates import (
            generate_fixed_closing,
            generate_fixed_opening,
        )

        entries = [
            {
                "category": "安全",
                "editor_angle": "Meta AI客服泄露账号权限",
                "title_translation": "Meta AI客服被滥用",
                "signal": "AI客服变成新的攻击面",
                "why_it_matters": "AI产品权限边界会影响真实用户安全",
                "keywords": ["AI安全"],
                "score": 100,
                "comment_count": 20,
                "coverage_tier": "focus",
            },
            {
                "category": "硬件",
                "editor_angle": "Nvidia把CPU塞进Windows PC",
                "title_translation": "Nvidia Windows PC方案",
                "signal": "本地AI硬件开始变成平台之争",
                "why_it_matters": "本地AI会改变PC硬件和平台控制权",
                "keywords": ["Windows PC"],
                "score": 80,
                "comment_count": 30,
                "coverage_tier": "focus",
            },
        ]

        opening = generate_fixed_opening("2026-06-07", highlight_entries=entries)
        closing = generate_fixed_closing("2026-06-07", entries)

        assert opening.audio_text.startswith("昨天，")
        assert "HN社区在讨论" in opening.audio_text
        assert "早上好" in opening.audio_text
        assert "祝你今天顺利" in closing.audio_text
        assert "？" not in closing.audio_text

    def test_opening_and_closing_do_not_inject_thesis_templates(self):
        from src.pipeline.script.templates import _closing_audio, _opening_audio

        entries = [
            {"category": "安全", "editor_angle": "AI客服漏洞", "signal": "AI客服漏洞"},
            {
                "category": "硬件",
                "editor_angle": "Nvidia新CPU",
                "signal": "Nvidia新CPU",
            },
            {
                "category": "资本",
                "editor_angle": "Anthropic融资",
                "signal": "Anthropic融资",
            },
        ]

        audio = _opening_audio(entries) + _closing_audio(entries, weekday=2)

        assert "今天的主线" not in audio
        assert "风险开始外溢" not in audio
        assert "控制权和兜底成本" not in audio
        assert "代价由谁承担" not in audio
        assert "HN社区在讨论AI客服漏洞、Nvidia新CPU、Anthropic融资" in audio
        assert "今天的HN速览就到这里" in audio

    def test_closing_audio_uses_weekend_tail_on_friday_saturday(self):
        from src.pipeline.script.templates import _closing_audio

        entries = [{"category": "硬件", "editor_angle": "Nvidia本地CPU"}]
        assert "周末也祝你休息顺利" in _closing_audio(entries, weekday=4)
        assert "周末也祝你休息顺利" in _closing_audio(entries, weekday=5)
        assert "祝你今天顺利" in _closing_audio(entries, weekday=2)

    def test_closing_audio_uses_date_aware_greeting(self):
        from datetime import date

        from src.pipeline.script.templates import _closing_audio

        entries = [{"category": "硬件", "editor_angle": "Nvidia本地CPU"}]

        assert "国庆假期也祝你休息顺利" in _closing_audio(
            entries, weekday=3, day=date(2026, 10, 1)
        )
        assert "年底也祝你收尾顺利" in _closing_audio(
            entries, weekday=1, day=date(2026, 12, 29)
        )
        assert "月末也祝你收尾顺利" in _closing_audio(
            entries, weekday=1, day=date(2026, 6, 30)
        )

    def test_closing_audio_omits_story_details_from_audio_text(self):
        from src.pipeline.script.templates import _closing_audio

        entries = [
            {
                "category": "游戏产业",
                "signal": "Steam更新砍掉P2P直连",
                "editor_angle": "Steam Networking让中东玩家吃中继延迟",
            },
            {
                "category": "数字消费",
                "signal": "停服即作废",
                "editor_angle": "Stop Killing Games追问数字所有权",
            },
        ]

        audio = _closing_audio(entries, weekday=1)

        # Story-specific details belong in the visual ClosingCard, not the audio.
        assert "Steam" not in audio
        assert "停服即作废" not in audio
        assert "就到这里" in audio
        assert "？" not in audio
        assert "工具效率变快后的成本问题" not in audio

    def test_opening_keeps_story_hooks_without_thesis_injection(self):
        from src.pipeline.script.templates import _opening_audio, _closing_audio

        entries = [
            {
                "category": "基础设施",
                "signal": "Steam更新砍掉P2P直连",
                "editor_angle": "Steam Networking让中东玩家吃中继延迟",
            },
            {
                "category": "其他",
                "signal": "停服即作废",
                "editor_angle": "Stop Killing Games追问数字所有权",
                "keywords": ["数字所有权"],
            },
            {
                "category": "开发者体验",
                "signal": "Claude Desktop缺Linux官方版",
                "editor_angle": "Anthropic被要求发布Linux构建",
            },
        ]

        opening = _opening_audio(entries)
        closing = _closing_audio(entries, weekday=0)

        assert "Steam更新砍掉P2P直连" in opening
        assert "停服即作废" in opening
        assert "Claude Desktop" in opening
        assert "控制权和兜底成本" not in opening
        assert "控制权和兜底成本" not in closing
        assert "开发者工具正在变快" not in opening

    def test_compact_copy_normalizes_then_compacts_without_ellipsis(self):
        from src.pipeline.script.templates import _compact_copy

        # CJK↔ASCII spaces get tightened first
        assert _compact_copy("Meta 自家 AI 大模型", 14) == "Meta自家AI大模型"
        # Short input passes through unchanged
        assert _compact_copy("短的", 14) == "短的"
        # Over-length gets compacted without adding ellipsis
        out = _compact_copy("这是一个非常非常长的副标题需要被截断处理一下", 14)
        assert len(out) <= 14
        assert "…" not in out
        # None / empty safe
        assert _compact_copy("", 14) == ""
        assert _compact_copy(None, 14) == ""

    def test_entry_hook_falls_back_through_keys(self):
        from src.pipeline.script.templates import _entry_hook

        # signal wins; with no clause separator, noise stripping keeps the tail
        assert _entry_hook({"signal": "评论区正在变成新的攻击面"}) == "新的攻击面"
        # editor_angle with a clause separator: split first, then strip
        assert (
            _entry_hook({"editor_angle": "Nvidia本地CPU：Windows PC新方案"})
            == "Nvidia本地CPU"
        )
        # then title_translation (no separator, no noise)
        assert (
            _entry_hook({"title_translation": "Anthropic融资递表"})
            == "Anthropic融资递表"
        )
        # then original_title; long enough to trigger compaction
        assert _entry_hook({"original_title": "Some English Title"}) == "Some English"
        # finally the placeholder when nothing is provided
        assert _entry_hook({}) == "技术信号"

    def test_entry_hook_strips_noise_tokens_safely(self):
        from src.pipeline.script.templates import _entry_hook

        # "评论区" and "变成" are noise; result should still be meaningful
        out = _entry_hook({"signal": "评论区 正在 变成 新的攻击面"})
        # After clause split on spaces (no separator), only noise strip applies
        assert "评论区" not in out
        assert "变成" not in out

    def test_opening_audio_does_not_ellipsize_spoken_hooks(self):
        from src.pipeline.script.templates import _opening_audio

        entries = [
            {
                "signal": "LLM正把专家工程师拉平成可复制的提示词操作者",
                "editor_angle": "十年支付后端工程师称三大专业壁垒已被LLM逐个击穿",
                "keywords": ["Claude Code", "MCP协议"],
            },
            {
                "signal": "多智能体写代码的瓶颈不在生成，而在反复评审吃掉的token。",
                "editor_angle": "ChatDev跑30个SDLC任务发现评审吃掉六成token",
                "keywords": ["Token消耗"],
            },
            {
                "signal": "游戏停服后玩家一无所有，立法和钱包投票到底谁管用",
                "editor_angle": "玩家发起运动迫使欧盟与立法机构介入游戏停运争议",
                "keywords": ["Stop Killing Games"],
            },
        ]

        audio = _opening_audio(entries)

        assert "…" not in audio
        assert audio.startswith("昨天，")
        assert "早上好" in audio
        assert "可复制的提" not in audio
        assert "立法机" not in audio
        assert "Claude Code" in audio

    def test_spoken_hook_prefers_complete_fallback_over_truncated_phrase(self):
        from src.pipeline.script.templates import _entry_spoken_hook

        out = _entry_spoken_hook(
            {
                "signal": "LLM正把专家工程师拉平成可复制的提示词操作者",
                "editor_angle": "十年支付后端工程师称三大专业壁垒已被LLM逐个击穿",
                "keywords": ["Claude Code", "MCP协议"],
            }
        )

        assert out == "Claude Code"
