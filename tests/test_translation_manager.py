from unittest.mock import MagicMock

from src.core.models import (
    ContentComment,
    ContentItem,
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
)
from src.pipeline.translation_manager import TranslationManager


def _make_manager():
    return TranslationManager(
        llm_provider=MagicMock(),
        content_preparer=MagicMock(),
        config={"logging": {"level": "WARNING"}},
    )


def test_collect_comment_refs_uses_selected_ids_then_fills_to_three():
    content = ContentPackage(
        date="2026-05-11",
        items=[
            ContentItem(
                source="hn",
                source_id="story",
                title="Story",
                url=None,
                comments=[
                    ContentComment(
                        author="linker",
                        content="Here is an article about writing portable ARM64 assembly: https://ariadne.space/2023/04/12/writing-portable-arm-assembly/",
                        source_id="link",
                        quality_score=0.95,
                    ),
                    ContentComment(
                        author="skeptic",
                        content="The hard part is not the syntax, it is keeping ABI assumptions and toolchain behavior consistent across platforms.",
                        source_id="view",
                        quality_score=0.7,
                        sentiment=-0.4,
                    ),
                    ContentComment(
                        author="operator",
                        content="In production this usually fails at the boundary where deployment scripts assume one platform and users bring another.",
                        source_id="ops",
                        quality_score=0.65,
                    ),
                    ContentComment(
                        author="supporter",
                        content="I like the goal, but it should document the unsupported cases clearly instead of pretending portability is automatic.",
                        source_id="support",
                        quality_score=0.6,
                        sentiment=0.5,
                    ),
                ],
            )
        ],
    )
    script = Script(
        title="T",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text="",
                duration=1,
                scene_elements=[
                    SceneElement(
                        element_type="quote_card",
                        start_time=0.0,
                        end_time=5.0,
                        props={"story_index": 0, "selected_comment_ids": ["view"]},
                    )
                ],
            )
        ],
    )
    manager = _make_manager()
    refs = manager.collect_comment_refs(
        content,
        manager._selected_ids_by_story(script),
    )
    # select_quote_comments orders by stance: 支持, 质疑, 中立
    assert list(refs.keys()) == [
        "comment_story_support",
        "comment_story_view",
        "comment_story_ops",
    ]
    assert "link" not in "".join(refs.keys())


def test_apply_translations_to_script_uses_judgement_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-05-11",
        items=[
            ContentItem(
                source="hn",
                source_id="story",
                title="Story",
                url=None,
                comments=[
                    ContentComment(
                        author="plain",
                        content="This neutral comment has enough explanation to be a fallback choice.",
                        source_id="plain",
                        quality_score=0.6,
                    ),
                    ContentComment(
                        author="judge",
                        content="This judged comment has a sharper viewpoint and should receive the cached translation.",
                        source_id="judged",
                        quality_score=0.5,
                    ),
                ],
            )
        ],
    )
    judgement_path = tmp_path / "data" / "2026-05-11" / "comment_judgement.json"
    judgement_path.parent.mkdir(parents=True)
    judgement_path.write_text(
        """
{
  "schema_version": 2,
  "stories": {
    "story": {
      "comment_lanes": {
        "representative": [
          {
            "comment_id": "judged",
            "role": "experience",
            "stance": "中立",
            "claim": "缓存翻译跟着精选走",
            "quote_score": 0.9
          }
        ]
      },
      "quote_candidates": [
        {
          "comment_id": "judged",
          "quote_score": 0.9,
          "has_viewpoint": true,
          "reject_for_quote": false
        }
      ]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )
    script = Script(
        title="T",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text="",
                duration=1,
                scene_elements=[
                    SceneElement(
                        element_type="atmosphere_card",
                        start_time=0.0,
                        end_time=5.0,
                        props={
                            "story_index": 0,
                            "quotes": [
                                {
                                    "source_id": "judged",
                                    "text": "This judged comment has a sharper viewpoint and should receive the cached translation.",
                                }
                            ],
                        },
                    )
                ],
            )
        ],
    )

    TranslationManager.apply_translations_to_script(
        script,
        content,
        {"comment_story_judged": "这条被 judgement 选中的评论应该有翻译。"},
    )

    quote = script.segments[0].scene_elements[0].props["quotes"][0]
    assert quote["text_cn"] == "这条被 judgement 选中的评论应该有翻译。"
