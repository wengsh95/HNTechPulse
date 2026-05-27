import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Dict


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge override into base. Nested dicts are merged, not replaced."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(config_path: str = "config/") -> Dict[str, Any]:
    load_dotenv()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    if path.is_dir():
        config: Dict[str, Any] = {}
        yaml_files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
        if not yaml_files:
            raise FileNotFoundError(f"No YAML files found in: {config_path}")
        for yaml_file in yaml_files:
            with open(yaml_file, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if data:
                    _deep_merge(config, data)
        return config

    with open(path, "r", encoding="utf-8") as cfg_f:
        return yaml.safe_load(cfg_f)


def get_env(key: str, default: Any = None) -> Any:
    return os.getenv(key, default)
