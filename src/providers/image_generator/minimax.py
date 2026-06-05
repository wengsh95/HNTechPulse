"""MiniMax image generation provider.

Implements :class:`ImageGeneratorProvider` against the MiniMax
`POST /v1/image_generation` endpoint. Returns a URL by default; the
provider downloads the image bytes and writes them to ``output_path``.
"""

import json
from pathlib import Path
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import ImageGeneratorProvider
from src.core.models import ImageResult
from src.utils.config import get_env
from src.utils.logger import setup_logger


_API_URL = "https://api.minimaxi.com/v1/image_generation"

# Pixel dimensions for each supported aspect ratio (per API docs).
_ASPECT_RATIO_DIMS = {
    "1:1": (1024, 1024),
    "4:3": (1152, 864),
    "16:9": (1280, 720),
    "3:2": (1248, 832),
    "2:3": (832, 1248),
    "3:4": (864, 1152),
    "9:16": (720, 1280),
    "21:9": (1344, 576),
}


class MinimaxImageGenerator(ImageGeneratorProvider):
    def __init__(self, config: dict, debug: bool = False, **kwargs):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        img_cfg = config.get("image_generator", {})
        self.model = img_cfg.get("model", "image-01")
        self.aspect_ratio = img_cfg.get("aspect_ratio", "4:3")
        self.n = int(img_cfg.get("n", 1))
        self.prompt_optimizer = bool(img_cfg.get("prompt_optimizer", False))
        self.response_format = img_cfg.get("response_format", "url")
        self.api_key = img_cfg.get("api_key") or get_env("MINIMAX_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MiniMax image generator requires MINIMAX_API_KEY in environment "
                "or image_generator.api_key config"
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def generate(self, prompt: str, output_path: str, **kwargs: Any) -> ImageResult:
        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        n = int(kwargs.get("n", self.n))
        seed = kwargs.get("seed")
        response_format = kwargs.get("response_format", self.response_format)

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": response_format,
            "n": n,
            "prompt_optimizer": self.prompt_optimizer,
        }
        if seed is not None:
            payload["seed"] = seed

        self.logger.info(
            f"Generating image (model={self.model}, aspect={aspect_ratio}, n={n})"
        )

        resp = self._session.post(_API_URL, data=json.dumps(payload), timeout=120)
        resp.raise_for_status()
        data = resp.json()

        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code")
        if status_code not in (None, 0):
            raise RuntimeError(
                f"MiniMax image generation failed: "
                f"{base_resp.get('status_msg')} (code={status_code})"
            )

        width, height = _ASPECT_RATIO_DIMS.get(aspect_ratio, (1152, 864))
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if response_format == "base64":
            import base64

            b64_list = (data.get("data") or {}).get("image_base64") or []
            if not b64_list:
                raise RuntimeError("MiniMax image generation returned no base64 data")
            out.write_bytes(base64.b64decode(b64_list[0]))
        else:
            url_list = (data.get("data") or {}).get("image_urls") or []
            if not url_list:
                raise RuntimeError("MiniMax image generation returned no image URLs")
            img_resp = self._session.get(url_list[0], timeout=60)
            img_resp.raise_for_status()
            out.write_bytes(img_resp.content)

        metadata = {
            "prompt": prompt,
            "model": self.model,
            "aspect_ratio": aspect_ratio,
            "task_id": data.get("id"),
            "success_count": (data.get("metadata") or {}).get("success_count"),
            "failed_count": (data.get("metadata") or {}).get("failed_count"),
        }
        self.logger.info(f"Image written to {out} ({width}x{height})")

        return ImageResult(
            path=str(out),
            width=width,
            height=height,
            provider="minimax",
            metadata=metadata,
        )
