from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from src.core.models import ContentItem, ContentPackage
from src.pipeline.paths import (
    media_images_dir,
    pipeline_path,
    publish_path,
    publish_xhs_cards_dir,
)
from src.pipeline.xhs_cards import (
    CARD_ROLES,
    plan_xhs_cards,
    render_xhs_cards,
    xhs_card_set_is_fresh,
)
from src.utils.atomic_io import atomic_write_json


def _content() -> ContentPackage:
    return ContentPackage(
        date="2026-07-27",
        items=[
            ContentItem(
                source="hackernews",
                source_id="123",
                title="A release changes developer workflows",
                title_cn="一次发布改变开发流程",
                url="https://example.com/story",
                score=420,
                comment_count=180,
                editorial_score=30.0,
                category="AI",
                editor_angle="工具把三个手工步骤合并成一个工作流",
                article_summary="该工具发布了新的自动化工作流，并解释了迁移边界。",
                key_points=[
                    {"point": "新流程减少手工切换"},
                    {"point": "旧接口仍然保留"},
                    {"point": "迁移需要显式确认"},
                    {"point": "社区担心默认行为"},
                ],
                why_it_matters="开发者需要重新评估自动化边界",
            )
        ],
    )


def _write_inputs(date: str, content: ContentPackage) -> None:
    atomic_write_json(
        pipeline_path(date, "content.json"),
        {"date": date, "items": [{"source_id": "123"}]},
    )
    atomic_write_json(
        pipeline_path(date, "comment_judgement.json"),
        {
            "stories": {
                "123": {
                    "debate_focus": ["默认行为", "迁移成本", "自动化边界"],
                    "stance_distribution": {"支持": 0.4, "质疑": 0.4, "中立": 0.2},
                    "quote_candidates": [
                        {
                            "comment_id": "c1",
                            "stance": "支持",
                            "claim": "少一次切换，日常工作流会顺很多",
                            "quote_score": 0.9,
                        },
                        {
                            "comment_id": "c2",
                            "stance": "质疑",
                            "claim": "默认自动化会让边界更难观察",
                            "quote_score": 0.8,
                        },
                        {
                            "comment_id": "c3",
                            "stance": "中立",
                            "claim": "关键仍然是迁移过程能否回退",
                            "quote_score": 0.7,
                        },
                    ],
                }
            }
        },
    )
    image_dir = media_images_dir(date)
    image_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), "#d9dde8").save(image_dir / "123.jpg")
    atomic_write_json(
        pipeline_path(date, "image_selection.json"),
        {
            "items": {
                "123": {
                    "selected_image": "images/123.jpg",
                    "candidates": [
                        {
                            "path": "images/123.jpg",
                            "origin_url": "https://example.com/123.jpg",
                        }
                    ],
                }
            }
        },
    )


def _planner() -> MagicMock:
    llm = MagicMock()
    llm.fast_model = "fast"
    llm.fast_temperature = 0.2
    llm.complete_prompt.return_value = {
        "focus_story_id": "123",
        "hook_title": "自动化终于少切三次",
        "hook_lead": "六页看清新流程带来的收益和边界",
        "evidence_title": "先看发布里写了什么",
        "evidence_points": ["减少手工切换", "旧接口仍保留", "迁移需要确认"],
        "breakdown_title": "变化发生在四个环节",
        "breakdown_points": ["入口合并", "状态集中", "回退保留", "默认行为改变"],
        "debate_title": "社区争的是默认边界",
        "quote_comment_ids": ["c1", "c2", "c3"],
        "quotes_title": "三种立场都很直接",
        "closing_title": "最后记住这四点",
        "takeaways": ["效率提升", "边界要看清", "迁移要能回退", "默认值最关键"],
        "question": "你愿意把多少步骤交给默认自动化？",
    }
    return llm


def test_plan_creates_one_story_six_card_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-07-27"
    content = _content()
    _write_inputs(date, content)

    deck = plan_xhs_cards(content, date, _planner(), {"llm": {}})

    assert deck["focus_story_id"] == "123"
    assert [card["role"] for card in deck["cards"]] == list(CARD_ROLES)
    assert deck["cards"][4]["quotes"][0]["claim"] == "少一次切换，日常工作流会顺很多"
    assert publish_path(date, "xhs_cards.json").exists()


def _has_browser() -> bool:
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]
    return any(path.exists() for path in candidates)


@pytest.mark.skipif(not _has_browser(), reason="Chrome/Edge is not installed")
def test_render_exports_six_1080x1440_cards(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-07-27"
    content = _content()
    _write_inputs(date, content)
    plan_xhs_cards(content, date, _planner(), {"llm": {}})

    paths = render_xhs_cards(date, {"llm": {}})

    assert len(paths) == 6
    assert xhs_card_set_is_fresh(date) is True
    assert (publish_xhs_cards_dir(date) / "_contact-sheet.png").exists()
    with Image.open(paths[0]) as image:
        assert image.size == (1080, 1440)
    sources = publish_xhs_cards_dir(date) / "assets" / "SOURCES.md"
    assert "https://example.com/123.jpg" in sources.read_text(encoding="utf-8")
