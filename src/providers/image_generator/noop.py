"""NoOp image generator — placeholder until mmx/external is wired.

Saves a placeholder PNG (solid color) at output_path so the pipeline
flow can be exercised end-to-end. Replace with a real mmx-backed
provider when mmx integration is ready.
"""

from pathlib import Path

from PIL import Image

from src.core.interfaces import ImageGeneratorProvider
from src.core.models import ImageResult


class NoOpImageGenerator(ImageGeneratorProvider):
    def __init__(self, config: dict, **kwargs):
        self.config = config

    def generate(self, prompt: str, output_path: str, **kwargs) -> ImageResult:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1920, 1080), color=(26, 26, 26))
        img.save(output_path)
        return ImageResult(
            path=output_path,
            width=1920,
            height=1080,
            provider="noop",
            metadata={"prompt": prompt, "note": "placeholder until mmx is wired"},
        )
