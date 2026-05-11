from unittest.mock import MagicMock

from src.core.models import ContentComment, ContentItem, ContentPackage, SceneElement, Script, ScriptSegment
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
                estimated_duration=1,
                scene_elements=[
                    SceneElement(
                        element_type="quote_card",
                        start_time=0,
                        end_time=1,
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
    assert list(refs.keys()) == [
        "comment_story_view",
        "comment_story_support",
        "comment_story_ops",
    ]
    assert "link" not in "".join(refs.keys())
