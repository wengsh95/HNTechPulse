"""Tests for src/providers/factory.py

The factory uses a declarative ``attempts`` list to auto-register every
provider that ships in the codebase. The contract:

1. After import, every provider with an installed SDK is in its registry.
2. ``create_X("unknown", ...)`` raises ``ValueError`` whose message lists
   the available providers (so a typo in config yields a useful error).
3. ``_auto_register`` swallows ``ImportError`` (SDK not installed) and
   ``AttributeError`` (class renamed) without crashing the app — so a
   partial install still boots, and a class rename is logged loudly but
   doesn't poison the whole factory.
"""

import importlib
from unittest.mock import patch

import pytest

from src.providers import factory as factory_mod
from src.providers.factory import (
    _IMAGE_GENERATOR_REGISTRY,
    _LLM_REGISTRY,
    _RENDERER_REGISTRY,
    _TTS_REGISTRY,
    _FETCHER_REGISTRY,
    _auto_register,
    create_fetcher,
    create_image_generator,
    create_llm_provider,
    create_renderer,
    create_tts_provider,
)


# ── Registry population (observable contract) ────────────────────────


class TestRegistryPopulated:
    """All providers shipped in src/providers/ should be in their registries
    after the module is imported (their SDKs are part of the project)."""

    def test_fetcher_registry_has_hn(self):
        assert "hn" in _FETCHER_REGISTRY
        from src.providers.fetcher.hn_fetcher import HNFetcher

        assert _FETCHER_REGISTRY["hn"] is HNFetcher

    def test_llm_registry_has_openai_and_minimax(self):
        from src.providers.llm.minimax import MiniMaxLLMProvider
        from src.providers.llm.openai import OpenAILLMProvider

        assert _LLM_REGISTRY["openai"] is OpenAILLMProvider
        assert _LLM_REGISTRY["minimax"] is MiniMaxLLMProvider

    def test_tts_registry_has_three_providers(self):
        from src.providers.tts.edge_tts import EdgeTTSProvider
        from src.providers.tts.mimo_tts import MimoTTSProvider
        from src.providers.tts.minimax_tts import MinimaxTTSProvider

        assert _TTS_REGISTRY["edge-tts"] is EdgeTTSProvider
        assert _TTS_REGISTRY["mimo"] is MimoTTSProvider
        assert _TTS_REGISTRY["minimax"] is MinimaxTTSProvider

    def test_renderer_registry_has_remotion_and_hyperframes(self):
        from src.providers.renderer.hyperframes_renderer import HyperFramesRenderer
        from src.providers.renderer.remotion_renderer import RemotionRenderer

        assert _RENDERER_REGISTRY["remotion"] is RemotionRenderer
        assert _RENDERER_REGISTRY["hyperframes"] is HyperFramesRenderer

    def test_image_generator_registry_has_noop_and_minimax(self):
        from src.providers.image_generator.minimax import MinimaxImageGenerator
        from src.providers.image_generator.noop import NoOpImageGenerator

        assert _IMAGE_GENERATOR_REGISTRY["noop"] is NoOpImageGenerator
        assert _IMAGE_GENERATOR_REGISTRY["minimax"] is MinimaxImageGenerator


# ── Unknown-name errors include available list ──────────────────────


class TestUnknownNameErrors:
    def test_fetcher_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc:
            create_fetcher("nonexistent", {})
        msg = str(exc.value)
        assert "Unknown fetcher" in msg
        assert "nonexistent" in msg
        assert "Available" in msg
        # Available list should mention the real fetcher
        assert "hn" in msg

    def test_llm_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc:
            create_llm_provider("nonexistent", {})
        msg = str(exc.value)
        assert "Unknown LLM provider" in msg
        # The two real providers should be in the available list
        assert "openai" in msg
        assert "minimax" in msg

    def test_tts_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc:
            create_tts_provider("nonexistent", {})
        msg = str(exc.value)
        assert "Unknown TTS provider" in msg
        assert "edge-tts" in msg
        assert "mimo" in msg
        assert "minimax" in msg

    def test_renderer_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc:
            create_renderer("nonexistent", {})
        msg = str(exc.value)
        assert "Unknown renderer" in msg
        assert "remotion" in msg
        assert "hyperframes" in msg

    def test_image_generator_unknown_lists_available(self):
        with pytest.raises(ValueError) as exc:
            create_image_generator("nonexistent", {})
        msg = str(exc.value)
        assert "Unknown image_generator" in msg
        assert "noop" in msg
        assert "minimax" in msg


# ── create_X happy paths (constructor invoked with right config) ────


class TestCreateHappyPath:
    def test_create_fetcher_instantiates(self):
        config = {"logging": {"level": "WARNING"}, "hn": {}}
        fetcher = create_fetcher("hn", config, debug=False)
        from src.providers.fetcher.hn_fetcher import HNFetcher

        assert isinstance(fetcher, HNFetcher)

    def test_create_tts_instantiates(self):
        config = {"logging": {"level": "WARNING"}, "tts": {}}
        tts = create_tts_provider("edge-tts", config)
        from src.providers.tts.edge_tts import EdgeTTSProvider

        assert isinstance(tts, EdgeTTSProvider)

    def test_create_renderer_instantiates(self):
        config = {
            "logging": {"level": "WARNING"},
            "video": {"resolution": (1280, 720), "fps": 24, "bg_color": "#000"},
            "remotion": {},
        }
        renderer = create_renderer("remotion", config)
        from src.providers.renderer.remotion_renderer import RemotionRenderer

        assert isinstance(renderer, RemotionRenderer)

    def test_create_image_generator_instantiates(self):
        config = {"logging": {"level": "WARNING"}}
        gen = create_image_generator("noop", config)
        from src.providers.image_generator.noop import NoOpImageGenerator

        assert isinstance(gen, NoOpImageGenerator)


# ── _auto_register resilience ────────────────────────────────────────


class TestAutoRegisterResilience:
    """``_auto_register`` must NOT crash the app on partial installs or
    a renamed class. It logs and moves on."""

    def test_import_error_is_swallowed(self):
        """Simulate a missing SDK: import_module raises ImportError, but
        the loop continues to the next attempt."""
        # Snapshot the existing registry state to know what was there
        snapshot = {
            "fetcher": dict(_FETCHER_REGISTRY),
            "llm": dict(_LLM_REGISTRY),
            "tts": dict(_TTS_REGISTRY),
            "renderer": dict(_RENDERER_REGISTRY),
            "image_generator": dict(_IMAGE_GENERATOR_REGISTRY),
        }

        # Spy on the factory's logger so we can assert what it logged.
        warning_calls: list[str] = []
        error_calls: list[str] = []

        def fake_warning(msg, *args, **kwargs):
            warning_calls.append(msg % args if args else msg)

        def fake_error(msg, *args, **kwargs):
            error_calls.append(msg % args if args else msg)

        with patch(
            "importlib.import_module",
            side_effect=ImportError("simulated missing SDK"),
        ):
            with (
                patch.object(factory_mod._logger, "warning", side_effect=fake_warning),
                patch.object(factory_mod._logger, "error", side_effect=fake_error),
            ):
                # Must not raise
                _auto_register()

        # ImportError should log at WARNING, not ERROR.
        assert error_calls == [], (
            f"ImportError should not produce ERROR logs, got: {error_calls}"
        )
        assert any("unavailable" in m for m in warning_calls), (
            f"Expected warning mentioning 'unavailable', got: {warning_calls}"
        )

        # Registries are unchanged from the snapshot (no re-registration
        # happened because every import failed).
        assert _FETCHER_REGISTRY == snapshot["fetcher"]
        assert _LLM_REGISTRY == snapshot["llm"]
        assert _TTS_REGISTRY == snapshot["tts"]
        assert _RENDERER_REGISTRY == snapshot["renderer"]
        assert _IMAGE_GENERATOR_REGISTRY == snapshot["image_generator"]

    def test_attribute_error_is_logged_at_error(self):
        """If a class is renamed/removed, the factory should log loudly
        (ERROR) but not raise — the agent can still use whatever DID
        register."""

        # Provide a fake module that has no class with the expected name
        class FakeModule:
            pass

        warning_calls: list[str] = []
        error_calls: list[str] = []

        with patch(
            "importlib.import_module",
            return_value=FakeModule(),
        ):
            with (
                patch.object(
                    factory_mod._logger,
                    "warning",
                    side_effect=lambda m, *a, **kw: warning_calls.append(
                        m % a if a else m
                    ),
                ),
                patch.object(
                    factory_mod._logger,
                    "error",
                    side_effect=lambda m, *a, **kw: error_calls.append(
                        m % a if a else m
                    ),
                ),
            ):
                # Must not raise
                _auto_register()

        # At least one ERROR-level log should mention "not found"
        assert any("not found" in m for m in error_calls), (
            f"Expected ERROR log with 'not found' phrase, got: {error_calls}"
        )
        assert warning_calls == [], (
            f"AttributeError should not produce WARNING logs, got: {warning_calls}"
        )

    def test_partial_failure_does_not_block_others(self):
        """If one provider's import fails, the loop must continue and
        the rest of the registry must still be populated."""
        # Make the LLM's openai module fail; everything else succeeds
        real_import = importlib.import_module

        def selective_fake(name, *args, **kwargs):
            if name == "src.providers.llm.openai":
                raise ImportError("simulated openai missing")
            return real_import(name, *args, **kwargs)

        warning_calls: list[str] = []

        with patch("importlib.import_module", side_effect=selective_fake):
            with (
                patch.object(
                    factory_mod._logger,
                    "warning",
                    side_effect=lambda m, *a, **kw: warning_calls.append(
                        m % a if a else m
                    ),
                ),
                patch.object(
                    factory_mod._logger, "error", side_effect=lambda *a, **kw: None
                ),
            ):
                _auto_register()

        # The warnings list mentions "openai" as unavailable.
        assert any("openai" in m and "unavailable" in m for m in warning_calls), (
            f"Expected warning about 'openai' being unavailable, got: {warning_calls}"
        )


# ── Defense in depth: re-importing the module is safe ───────────────


class TestModuleReimportSafety:
    def test_reimport_does_not_double_register(self):
        """Re-running ``_auto_register`` is safe — each (kind, name) just
        overwrites the same registry slot. Pin that contract so we
        notice if a future change starts appending (which would break
        ``Unknown X: name. Available: [...]`` with duplicates)."""
        from src.providers.fetcher.hn_fetcher import HNFetcher

        before = set(_FETCHER_REGISTRY.keys())
        _auto_register()
        after = set(_FETCHER_REGISTRY.keys())
        assert before == after
        assert _FETCHER_REGISTRY["hn"] is HNFetcher

    def test_factory_module_idempotent(self):
        """Reimporting the module is a no-op observable side effect."""
        importlib.reload(factory_mod)
        # Should still be importable and registries still populated
        assert "hn" in factory_mod._FETCHER_REGISTRY
        assert "openai" in factory_mod._LLM_REGISTRY
