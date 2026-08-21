from src.core.models import (
    ContentItem,
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
)
from src.pipeline.paths import pipeline_path
from src.pipeline.transcript_generator import generate_brief_transcript, save_transcript


def _script() -> Script:
    return Script(
        title="Test",
        description="今天的简介",
        tags=[],
        total_duration=125,
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="开场口播",
                duration=5,
                scene_elements=[
                    SceneElement(
                        "cover_card",
                        0,
                        5,
                        {
                            "highlight_entries": [
                                {
                                    "rank": 1,
                                    "original_title": "Original",
                                    "title_cn": "焦点故事",
                                    "score": 100,
                                    "comment_count": 20,
                                }
                            ]
                        },
                    )
                ],
            ),
            ScriptSegment(
                segment_type="story_scan",
                audio_text="故事口播",
                duration=10,
                scene_elements=[
                    SceneElement(
                        "event_card",
                        0,
                        5,
                        {"story_index": 0, "dek": "事件摘要"},
                    ),
                    SceneElement(
                        "comment_dual_card",
                        5,
                        10,
                        {
                            "story_index": 0,
                            "left_summary": "支持观点",
                            "right_summary": "质疑观点",
                            "left_label": "支持",
                            "right_label": "质疑",
                            "stance_distribution": {"支持": 0.6, "质疑": 0.4},
                            "debate_focus": ["成本"],
                            "quotes": [
                                {"stance": "支持", "author": "u", "text": "评论"}
                            ],
                        },
                    ),
                ],
                meta={"sub_segment_subtitle_texts": [["故事字幕"]]},
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="速览口播",
                duration=5,
                scene_elements=[
                    SceneElement(
                        "quick_card",
                        0,
                        5,
                        {
                            "title": "速览标题",
                            "fact": "速览事实。",
                            "source_url": "https://quick.example",
                        },
                    )
                ],
            ),
            ScriptSegment(segment_type="closing", audio_text="结尾口播", duration=3),
        ],
    )


def test_generate_brief_transcript_includes_current_video_sections():
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="1",
                title="Original",
                url="https://story.example",
                score=100,
                comment_count=20,
                article_images=["https://image.example/a.png"],
            )
        ],
    )

    result = generate_brief_transcript(_script(), "2026-04-26", content)

    assert "# HN每日观察 | 2026-04-26" in result
    assert "> 视频时长 2:05" in result
    assert "## 今日亮点" in result
    assert "## 逐条速览" in result
    assert "**社区观点**" in result
    assert "**争议焦点**" in result
    assert "**社区对照**" in result
    assert "## 速览" in result
    assert "[原文](https://quick.example)" in result
    assert "## 结尾" in result


def test_generate_brief_transcript_falls_back_to_content_highlights():
    script = Script(
        title="Test",
        description="",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="开场", duration=1)],
    )
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="1",
                title="Original",
                url="https://story.example",
                title_cn="中文标题",
                score=50,
                comment_count=2,
            )
        ],
    )

    result = generate_brief_transcript(script, "2026-04-26", content)

    assert "**中文标题** / Original" in result


def test_save_transcript_writes_pipeline_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    path = save_transcript(_script(), "2026-04-26")

    assert path == pipeline_path("2026-04-26", "transcript.md")
    assert path.exists()
    assert "## 结尾" in path.read_text(encoding="utf-8")
