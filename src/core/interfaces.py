from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from .models import Script, ContentPackage, WordTiming, ScriptSegment


class ContentFetcher(ABC):
    """内容获取抽象（支持 HN/Reddit/Twitter 等）"""

    @abstractmethod
    def fetch(self, date: str, **kwargs) -> "ContentPackage":
        pass


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
        comments_data: Optional[dict] = None
    ) -> "ScriptSegment":
        """R2: 为单个 story 生成对应的 ScriptSegment"""
        pass

    @abstractmethod
    def translate_titles(self, content: "ContentPackage", prompt_template: str) -> "ContentPackage":
        """翻译所有故事标题"""
        pass

    @abstractmethod
    def translate_comments(self, content: "ContentPackage", comment_refs: dict) -> dict:
        """翻译指定评论，返回 {comment_{story}_{idx}: 译文} 字典"""
        pass


class TTSResult:
    """TTS 合成结果"""

    def __init__(
        self,
        duration: float,
        word_timings: Optional["List[WordTiming]"] = None,
        timing_level: str = "word",
    ):
        self.duration = duration
        self.word_timings = word_timings or []
        self.timing_level = timing_level


class TTSProvider(ABC):
    """TTS 抽象"""

    @abstractmethod
    def synthesize(self, text: str, output_path: str, emotion: str = None) -> "TTSResult":
        """合成音频，返回 TTSResult（包含时长和词级时间戳）"""
        pass


class Renderer(ABC):
    """渲染器抽象"""

    @abstractmethod
    def render(self, script: "Script", audio_dir: str, output_path: str, content: Optional["ContentPackage"] = None, date: str = "") -> None:
        pass

    def preview(self, script: "Script", audio_dir: str, content: Optional["ContentPackage"] = None) -> None:
        """启动预览模式（可选实现）。"""
        pass
