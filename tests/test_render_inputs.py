from types import SimpleNamespace

from src.pipeline import render_inputs


def test_build_render_inputs_keeps_shared_cache_fingerprint(monkeypatch):
    monkeypatch.setattr(
        render_inputs,
        "script_editorial_hash",
        lambda script: f"script:{script.title}",
    )
    monkeypatch.setattr(
        render_inputs,
        "pipeline_path",
        lambda date, name: f"{date}/{name}",
    )
    monkeypatch.setattr(
        render_inputs,
        "file_sha256",
        lambda path: f"hash:{path}",
    )

    content = SimpleNamespace(items=[1, 2])
    result = render_inputs.build_render_inputs(
        SimpleNamespace(title="Demo"), content, "2026-08-21", "FakeRenderer"
    )

    assert result == {
        "script_editorial_hash": "script:Demo",
        "audio_manifest_hash": "hash:2026-08-21/audio_manifest.json",
        "content_hash": "hash:2026-08-21/content.json",
        "renderer": "FakeRenderer",
        "content_item_count": 2,
    }
