from types import SimpleNamespace

from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.paths import media_images_dir, pipeline_path
from src.pipeline.story_images import prepare_story_images, require_story_images
from src.utils.atomic_io import atomic_write_json


def _script() -> Script:
    return Script(
        title="测试",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text="故事内容。",
                duration=2,
                scene_elements=[
                    SceneElement(
                        "event_card",
                        0,
                        1,
                        {"story_index": 0, "source_title": "故事标题"},
                    ),
                    SceneElement(
                        "atmosphere_card",
                        1,
                        2,
                        {"story_index": 0, "source_title": "故事标题"},
                    ),
                ],
            )
        ],
    )


def _content(image_paths: list[str] | None = None):
    item = SimpleNamespace(
        source_id=123,
        title="故事标题",
        url="https://example.com/story",
        article_images=image_paths or [],
        screenshot_image=None,
        logo_image=None,
        image_candidates=[],
    )
    return SimpleNamespace(items=[item])


def test_agent_mode_blocks_until_a_story_image_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = prepare_story_images(_script(), _content(), "2026-08-18", agent_mode=True)

    assert result.pending[0]["story_id"] == "123"
    assert result.stories[0]["status"] == "missing"
    assert "image_src" not in _script().segments[0].scene_elements[0].props


def test_non_agent_mode_selects_a_local_candidate_and_attaches_it(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    image_dir = media_images_dir("2026-08-18")
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "story.jpg").write_bytes(b"image")

    script = _script()
    result = prepare_story_images(
        script,
        _content(["images/story.jpg"]),
        "2026-08-18",
        agent_mode=False,
    )

    assert result.pending == []
    assert result.stories[0]["status"] == "ok"
    assert result.stories[0]["selected_image"] == "images/story.jpg"
    assert script.segments[0].scene_elements[0].props["image_src"] == "images/story.jpg"
    assert "image_src" not in script.segments[0].scene_elements[1].props


def test_agent_mode_accepts_only_the_confirmed_local_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image_dir = media_images_dir("2026-08-18")
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "story.jpg").write_bytes(b"image")
    atomic_write_json(
        pipeline_path("2026-08-18", "image_selection.json"),
        {
            "date": "2026-08-18",
            "items": {
                "123": {
                    "selected_image": "images/story.jpg",
                    "selection_source": "agent",
                }
            },
        },
    )

    script = _script()
    result = prepare_story_images(
        script,
        _content(["images/story.jpg"]),
        "2026-08-18",
        agent_mode=True,
    )

    assert result.pending == []
    assert result.stories[0]["status"] == "ok"
    assert (
        script.segments[0].scene_elements[0].props["story_image"] == "images/story.jpg"
    )
    assert "story_image" not in script.segments[0].scene_elements[1].props


def test_render_gate_rejects_a_script_with_no_story_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    try:
        require_story_images(_script(), "2026-08-18")
    except ValueError as exc:
        assert "Every story requires" in str(exc)
    else:
        raise AssertionError("missing story image should fail the render gate")
