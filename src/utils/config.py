import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Dict


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    load_dotenv()

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_env(key: str, default: Any = None) -> Any:
    return os.getenv(key, default)
