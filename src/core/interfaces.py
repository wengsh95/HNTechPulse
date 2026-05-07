from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from .models import Script, ContentPackage, SelectionResult, StoryAnalysis, WordTiming


class ContentFetcher(ABC):
    """内容获取抽象（支持 HN/Reddit/Twitter 等）"""

    @abstractmethod
    def fetch(self, date: str, **kwargs) -> "ContentPackage":
        pass


class LLMProvider(ABC):
    """LLM 抽象 —— 多轮调用模式 (R1a: 逐条分析 → R1b: 全局决策 → R2: 脚本生成)"""

    @abstractmethod
    def generate_selection(
        self,
        content: "ContentPackage",
        analyze_prompt_template: str,
        decision_prompt_template: str
    ) -> "SelectionResult":
        """
        Round 1 完整流程：
        R1a: 对每条 story 并发分析 → List[StoryAnalysis]
        R1b: 基于分析结果做全局选题决策 → SelectionResult
        """
        pass

    @abstractmethod
    def generate_script(
        self,
        selection: "SelectionResult",
        comments_json: str,
        script_prompt_template: str,
        date: str,
        product: str = "full"
    ) -> "Script":
        """Round 2: 基于选题结果 + 精选评论 → 完整脚本"""
        pass

    @abstractmethod
    def build_comments_json(self, content: "ContentPackage", selection: "SelectionResult") -> str:
        """根据选题结果提取精选评论原文，构建 Round 2 输入"""
        pass

    @abstractmethod
    def translate_selection(self, content: "ContentPackage", selection: "SelectionResult", prompt_template: str) -> "ContentPackage":
        """翻译选中内容的标题和评论，回填到 ContentPackage 中"""
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
