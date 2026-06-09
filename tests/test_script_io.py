from pathlib import Path

from src.core.models import Script
from src.pipeline.script.io import load_script, save_script_to_path


def test_script_io_preserves_cover_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/2026-06-08/script.json")
    script = Script(
        title="发布标题",
        description="简介",
        tags=["AI"],
        segments=[],
        cover_subtitle="— 审查成本\n— Steam延迟",
        cover_title="AI写代码贵在审查",
        cover_tags=["六成Token", "Steam延迟"],
    )

    save_script_to_path(script, path, date="2026-06-08")
    loaded = load_script("2026-06-08")

    assert loaded.cover_subtitle == "— 审查成本\n— Steam延迟"
    assert loaded.cover_title == "AI写代码贵在审查"
    assert loaded.cover_tags == ["六成Token", "Steam延迟"]
