import pytest

from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.human_review import (
    approve_current_script,
    generate_script_review_page,
    script_approval_is_current,
)
from src.pipeline.script.io import save_script


def _script(text: str = "一条经过审校的技术新闻。") -> Script:
    return Script(
        title="每日技术简报",
        description="描述",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text=text,
                duration=3.0,
                scene_elements=[
                    SceneElement(
                        element_type="event_card",
                        start_time=0.0,
                        end_time=3.0,
                        props={
                            "title_cn": "测试故事",
                            "subtitle_texts": [text],
                        },
                    )
                ],
                meta={"sub_segment_subtitle_texts": [[text]]},
            )
        ],
    )


def test_review_page_and_approval_are_bound_to_script_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-08-18"
    script = _script()
    save_script(script, date)

    page = generate_script_review_page(script, date)
    assert page.exists()
    assert "文案人工审查" in page.read_text(encoding="utf-8")
    assert not script_approval_is_current(date, script)

    approval = approve_current_script(date, reviewer="editor")
    assert approval.exists()
    assert script_approval_is_current(date, script)

    changed = _script("人工又改了一句，所以旧批准必须失效。")
    save_script(changed, date)
    assert not script_approval_is_current(date, changed)


def test_cannot_approve_a_stale_review_page(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-08-18"
    script = _script()
    save_script(script, date)
    generate_script_review_page(script, date)

    save_script(_script("页面生成后又改了文案。"), date)

    with pytest.raises(ValueError, match="missing or stale"):
        approve_current_script(date)
