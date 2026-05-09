from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, TypedDict


# ================= 数据源层 (特定于 HN) =================
# HNStory / HNComment 已移至 src/providers/fetcher/models.py


# ================= 中间层：通用素材模型 =================

@dataclass
class ContentComment:
    """一条评论（通用）"""
    author: str
    content: str
    content_cn: Optional[str] = None
    upvotes: Optional[int] = None


@dataclass
class ContentItem:
    """一条内容素材（通用，不依赖 HN）"""
    source: str
    source_id: str
    title: str
    url: Optional[str]
    summary: Optional[str] = None
    title_cn: Optional[str] = None
    score: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: int = 0
    comments: List[ContentComment] = field(default_factory=list)
    raw: Optional[Any] = None
    article_text: Optional[str] = None
    article_images: List[str] = field(default_factory=list)
    image_candidates: List[Dict[str, Any]] = field(default_factory=list)
    logo_image: Optional[str] = None
    screenshot_image: Optional[str] = None
    article_summary: Optional[str] = None
    # Where article_text came from: "aiohttp" | "headless" | "headed" | "manual_override" | "none" | "skipped" | "error" | "legacy".
    # "error" means enrichment threw an exception; see enrichment_error for reason.
    # "none" means no exception but no content was extracted.
    enrichment_source: Optional[str] = None
    # Populated only when enrichment_source == "error". Short human-readable reason.
    enrichment_error: Optional[str] = None


@dataclass
class ContentPackage:
    """给 LLM 的素材包（通用）"""
    date: str
    items: List[ContentItem]
    deep_dive_indices: List[int] = field(default_factory=list)
    brief_indices: List[int] = field(default_factory=list)
    quick_news_indices: List[int] = field(default_factory=list)


# ================= LLM 交互模型 =================

@dataclass
class StoryAnalysis:
    story_index: int
    raw_json: str = ""


@dataclass
class SelectionResult:
    brief_items: List[Dict[str, Any]] = field(default_factory=list)
    raw_json: str = ""


# ================= 灵活的视觉组件描述 =================

@dataclass
class SceneElement:
    """场景中的一个视觉元素（字幕、图片、气泡等）"""
    element_type: str
    start_time: float
    end_time: float
    props: Dict[str, Any]
    sub_segment_index: Optional[int] = None


@dataclass
class WordTiming:
    text: str
    start_time: float
    end_time: float


@dataclass
class Cue:
    """单个字幕提示"""
    text: str
    start_time: float
    end_time: float


@dataclass
class ScriptSegment:
    segment_type: str
    audio_text: str
    estimated_duration: float
    actual_duration: Optional[float] = None
    emotion: str = "neutral"

    scene_elements: List[SceneElement] = field(default_factory=list)
    meta: "SegmentMeta" = field(default_factory=dict)  # type: ignore[assignment]

    start_time: Optional[float] = None
    end_time: Optional[float] = None
    audio_path: Optional[str] = None
    cues: List[Cue] = field(default_factory=list)


class SegmentMeta(TypedDict, total=False):
    """Known keys stored on ScriptSegment.meta.

    All keys are optional (total=False) — not every segment populates every key.

    Keys:
        brief_items:     List of brief items surfaced in a story-scan segment.
        dashboard:       Dashboard element payload (overall summary card).
        story_title:     Human-readable story title, cached for display.
        word_timings:    Per-word timing data from TTS, used by renderer captions.
        timing_level:    "word" | "segment" — granularity of timing data.
        duration_ratio:  actual_duration / estimated_duration, computed post-TTS.
    """
    brief_items: List[Dict[str, Any]]
    dashboard: Any
    story_title: str
    word_timings: List[Dict[str, Any]]
    timing_level: str
    duration_ratio: float


@dataclass
class Script:
    title: str
    description: str
    tags: List[str]
    segments: List[ScriptSegment]
    total_duration: Optional[float] = None
