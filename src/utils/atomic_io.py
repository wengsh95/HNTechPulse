"""Atomic file I/O helpers.

Writes happen via a sibling ``.tmp`` file followed by an ``os.replace``, so a
crash mid-write can never leave a partial file in the destination path.
"""

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path | str, content: str, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` via a ``.tmp`` sibling + atomic rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def atomic_write_json(path: Path | str, data: Any, encoding: str = "utf-8") -> None:
    """Serialize ``data`` as JSON and atomically write to ``path``."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    atomic_write_text(path, text, encoding=encoding)
