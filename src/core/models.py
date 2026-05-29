from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


# ================= 数据源层 (特定于 HN) =================
# HNStory / HNComment 已移至 src/providers/fetcher/models.py


# ================= 中间层：通用素材模型 =================


@dataclass
class ContentComment:
    """一条评论（通用）"""

    author: str
    content: str
    content_cn: Optional[str] = None
    source_id: Optional[str] = None
    upvotes: Optional[int] = None
    depth: Optional[int] = None
    published_at: Optional[int] = None
    sentiment: Optional[float] = None
    quality_score: Optional[float] = None


@dataclass
class ContentItem:
    """一条内容素材（通用，不依赖 HN）"""

    source: str
    source_id: str
    title: str
    url: Optional[str]
    title_cn: Optional[str] = None
    score: Optional[int] = None
    comment_count: Optional[int] = None
    published_at: int = 0
    comments: List[ContentComment] = field(default_factory=list)
    article_text: Optional[str] = None
    article_images: List[str] = field(default_factory=list)
    image_candidates: List[Dict[str, Any]] = field(default_factory=list)
    logo_image: Optional[str] = None
    screenshot_image: Optional[str] = None
    article_summary: Optional[str] = None
    # EventCard fields extracted during enrichment
    editor_angle: Optional[str] = None
    dek: Optional[str] = None
    key_points: Optional[List[Dict[str, str]]] = None
    keywords: Optional[List[str]] = None
    category: Optional[str] = None
    why_it_matters: Optional[str] = None
    # Where article_text came from: "aiohttp" | "headless" | "headed" | "pdf" | "github_api" | "manual_override" | "downloaded_page" | "none" | "skipped" | "error" | "legacy".
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


# ================= LLM 交互模型 =================


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
class Cue:
    """单个字幕提示"""

    text: str
    start_time: float
    end_time: float


@dataclass
class ScriptSegment:
    segment_type: str
    audio_text: str
    duration: float
    actual_duration: Optional[float] = None
    emotion: str = "warm"

    scene_elements: List[SceneElement] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    start_time: Optional[float] = None
    end_time: Optional[float] = None
    audio_path: Optional[str] = None
    cues: List[Cue] = field(default_factory=list)


@dataclass
class Script:
    title: str
    description: str
    tags: List[str]
    segments: List[ScriptSegment]
    total_duration: Optional[float] = None
