import json

from src.core.models import (
    ContentComment,
    ContentItem,
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
)
from src.pipeline.agent_decision import AgentDecisionEngine
from src.pipeline.agent_variants import save_script_variant


def _config():
    return {
        "agent": {
            "decision": {
                "min_confidence_to_continue": 0.5,
                "min_factual_grounding": 0.7,
                "max_source_risk": 0.4,
                "min_script_publish_readiness": 0.7,
                "min_comments_for_discussion_only": 5,
            }
        }
    }


def _item(**kwargs):
    defaults = {
        "source": "hackernews",
        "source_id": "1",
        "title": "Story",
        "url": "https://example.com",
        "article_text": "Article body with enough context.",
        "comments": [],
    }
    defaults.update(kwargs)
    return ContentItem(**defaults)


def test_source_context_continues_with_article_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(date="2026-04-26", items=[_item()])

    result = AgentDecisionEngine(_config()).evaluate_source_context(
        content, content.date
    )

    assert result.status == "continue"
    assert result.scores["factual_grounding"] == 1.0
    decision_path = tmp_path / "data" / content.date / "agent_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["gate"] == "source_context"


def test_source_context_blocks_title_only_story(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[_item(article_text=None, article_summary=None, comments=[])],
    )

    result = AgentDecisionEngine(_config()).evaluate_source_context(
        content, content.date
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "insufficient_story_context"
    assert result.blocked_items[0]["comment_count"] == 0


def test_script_quality_blocks_weak_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            _item(
                comments=[
                    ContentComment(author=f"u{i}", content=f"comment {i}")
                    for i in range(5)
                ]
            )
        ],
    )
    script = Script(
        title="T",
        description="",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="", duration=1.0)],
    )

    result = AgentDecisionEngine(_config()).evaluate_script_quality(
        content, script, content.date
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "low_decision_confidence"


def test_select_script_variant_writes_decision_and_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[_item(article_text="solid source text")],
    )
    weak = Script(
        title="T",
        description="",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="", duration=1.0)],
    )
    strong = Script(
        title="Strong title",
        description="",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="open", duration=1.0),
            ScriptSegment(
                segment_type="story_scan",
                audio_text="story",
                duration=1.0,
                scene_elements=[
                    SceneElement(
                        element_type="atmosphere_card",
                        start_time=0,
                        end_time=1,
                        props={"selected_comment_ids": ["c1"]},
                    )
                ],
            ),
            ScriptSegment(segment_type="closing", audio_text="close", duration=1.0),
        ],
    )
    save_script_variant(
        content.date,
        "v01_weak",
        weak,
        label="Weak",
        strategy="weak",
    )
    save_script_variant(
        content.date,
        "v02_strong",
        strong,
        label="Strong",
        strategy="strong",
    )

    decision = AgentDecisionEngine(_config()).select_script_variant(
        content,
        [
            {
                "variant_id": "v01_weak",
                "label": "Weak",
                "strategy": "weak",
                "script": weak,
                "story_indices": [0],
                "preview": "",
            },
            {
                "variant_id": "v02_strong",
                "label": "Strong",
                "strategy": "strong",
                "script": strong,
                "story_indices": [0],
                "preview": "story",
            },
        ],
        content.date,
    )

    assert decision["status"] == "continue"
    assert decision["selected_variant"] == "v02_strong"
    selected_path = tmp_path / "data" / content.date / "selected_variant.json"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    assert selected["selected_variant"] == "v02_strong"
    brief_path = tmp_path / "data" / content.date / "variants" / "selection_brief.md"
    brief = brief_path.read_text(encoding="utf-8")
    assert "v02_strong" in brief
    assert "Agent Variant Selection" in brief
    scorecard_path = (
        tmp_path / "data" / content.date / "variants" / "v02_strong" / "scorecard.json"
    )
    assert (
        json.loads(scorecard_path.read_text(encoding="utf-8"))["status"] == "continue"
    )
