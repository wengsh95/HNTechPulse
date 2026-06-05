"""Image generation providers.

Entry point for cover/illustration generation. Concrete providers register
themselves into :mod:`src.providers.factory`.
"""

from src.providers.image_generator.noop import NoOpImageGenerator
from src.providers.image_generator.minimax import MinimaxImageGenerator

__all__ = ["NoOpImageGenerator", "MinimaxImageGenerator"]
