from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from .models import Script, ContentPackage, ScriptSegment, ImageResult


class ContentFetcher(ABC):
    """内容获取抽象（支持 HN/Reddit/Twitter 等）"""

    @abstractmethod
    def fetch(self, date: str, **kwargs) -> "ContentPackage":
        pass

    def fetch_comments(self, content: "ContentPackage", date: str) -> "ContentPackage":
        """Fetch comments for stories in content. Default: no-op."""
        return content

    def fetch_comment_preview(
        self,
        content: "ContentPackage",
        date: str,
        top_level_count: int = 5,
    ) -> "ContentPackage":
        """Fetch a small top-level comment preview for story prefiltering."""
        return content


class LLMProvider(ABC):
    """LLM 抽象 —— R2: 逐条生成脚本"""

    @abstractmethod
    def generate_single_story_segment(
        self,
        content: "ContentPackage",
        story_index: int,
        segment_type: str,
        prompt_template_path: str,
        date: str,
        comments_data: Optional[dict] = None,
        expected_card_types: Optional[list[str]] = None,
    ) -> "ScriptSegment":
        """R2: 为单个 story 生成对应的 ScriptSegment"""
        pass

    @abstractmethod
    def translate_titles(
        self, content: "ContentPackage", prompt_template: str, date: str = ""
    ) -> "ContentPackage":
        """翻译所有故事标题"""
        pass

    @abstractmethod
    def translate_comments(self, content: "ContentPackage", comment_refs: dict) -> dict:
        """翻译指定评论，返回 {comment_{story}_{idx}: 译文} 字典"""
        pass

    @abstractmethod
    def judge_story_comments(
        self,
        item,
        story_index: int,
        prompt_template_path: str = "prompts/comment_analyze.md",
        candidates=None,
    ) -> dict:
        """Rank comments suitable for quote display. Return {} if unsupported."""
        pass

    @abstractmethod
    def prefilter_stories(
        self,
        stories: list,
        prompt_template_path: str = "prompts/prefilter.md",
    ) -> list:
        """Judge technical relevance of stories. Returns list of {index, keep, reason}."""
        pass


class TTSResult:
    """TTS 合成结果"""

    def __init__(self, duration: float):
        self.duration = duration


class TTSProvider(ABC):
    """TTS 抽象"""

    @abstractmethod
    def synthesize(
        self, text: str, output_path: str, emotion: Optional[str] = None
    ) -> "TTSResult":
        """合成音频，返回 TTSResult"""
        pass


class Renderer(ABC):
    """渲染器抽象"""

    @abstractmethod
    def render(
        self,
        script: "Script",
        audio_dir: str,
        output_path: str,
        content: Optional["ContentPackage"] = None,
        date: str = "",
    ) -> None:
        pass

    def preview(
        self,
        script: "Script",
        audio_dir: str,
        content: Optional["ContentPackage"] = None,
        date: str = "",
    ) -> None:
        """启动预览模式（可选实现）。"""
        pass

    def sync_props(
        self,
        script: "Script",
        audio_dir: str,
        content: Optional["ContentPackage"] = None,
        date: str = "",
    ) -> None:
        """重新生成 props.json 和静态资源，不启动预览服务。"""
        pass

    @abstractmethod
    def write_props(
        self,
        script: "Script",
        audio_dir: str,
        content: Optional["ContentPackage"] = None,
        date: str = "",
    ) -> Tuple[Path, str]:
        """Prepare audio/image assets and write props.json. Returns (props_path, props_json)."""
        pass

    def cache_paths(self, date: str) -> List[Path]:
        """Renderer-specific cache directories to clean on --force.

        Default: empty list (no extra cache to clean). Renderers that write
        intermediate artifacts (chunk dirs, generated projects) should override.
        """
        return []


class ImageGeneratorProvider(ABC):
    """图像生成抽象 —— 用于封面/插图等场景。"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_path: str,
        **kwargs,
    ) -> "ImageResult":
        """根据 prompt 生成图像，写入 output_path，返回 ImageResult。"""
        pass
