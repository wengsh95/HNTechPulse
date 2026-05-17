from src.utils.logger import setup_logger


_FETCHER_REGISTRY = {}
_LLM_REGISTRY = {}
_TTS_REGISTRY = {}
_RENDERER_REGISTRY = {}

_logger = setup_logger(__name__)


def register_fetcher(name: str, cls):
    _FETCHER_REGISTRY[name] = cls


def register_llm(name: str, cls):
    _LLM_REGISTRY[name] = cls


def register_tts(name: str, cls):
    _TTS_REGISTRY[name] = cls


def register_renderer(name: str, cls):
    _RENDERER_REGISTRY[name] = cls


def _auto_register():
    """Import and register built-in providers.

    ImportError on an optional provider is logged (not swallowed) so a typo in
    the module or a genuinely broken import doesn't silently leave the registry
    empty. Unrelated providers still load.
    """
    attempts = [
        (
            "fetcher",
            "hn",
            "src.providers.fetcher.hn_fetcher",
            "HNFetcher",
            register_fetcher,
        ),
        (
            "llm",
            "openai",
            "src.providers.llm.openai",
            "OpenAILLMProvider",
            register_llm,
        ),
        (
            "tts",
            "edge-tts",
            "src.providers.tts.edge_tts",
            "EdgeTTSProvider",
            register_tts,
        ),
        ("tts", "mimo", "src.providers.tts.mimo_tts", "MimoTTSProvider", register_tts),
        (
            "tts",
            "minimax",
            "src.providers.tts.minimax_tts",
            "MinimaxTTSProvider",
            register_tts,
        ),
        (
            "renderer",
            "remotion",
            "src.providers.renderer.remotion_renderer",
            "RemotionRenderer",
            register_renderer,
        ),
    ]
    import importlib

    for kind, name, module_path, cls_name, register_fn in attempts:
        try:
            mod = importlib.import_module(module_path)
            register_fn(name, getattr(mod, cls_name))
        except ImportError as e:
            _logger.warning(
                f"{kind} provider '{name}' unavailable ({module_path}): {e}"
            )
        except AttributeError as e:
            _logger.error(
                f"{kind} provider '{name}': {cls_name} not found in {module_path}: {e}"
            )


_auto_register()


def create_fetcher(name: str, config: dict, **kwargs):
    if name not in _FETCHER_REGISTRY:
        raise ValueError(
            f"Unknown fetcher: {name}. Available: {list(_FETCHER_REGISTRY.keys())}"
        )
    return _FETCHER_REGISTRY[name](config, **kwargs)


def create_llm_provider(name: str, config: dict, **kwargs):
    if name not in _LLM_REGISTRY:
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {list(_LLM_REGISTRY.keys())}"
        )
    return _LLM_REGISTRY[name](config, **kwargs)


def create_tts_provider(name: str, config: dict, **kwargs):
    if name not in _TTS_REGISTRY:
        raise ValueError(
            f"Unknown TTS provider: {name}. Available: {list(_TTS_REGISTRY.keys())}"
        )
    return _TTS_REGISTRY[name](config, **kwargs)


def create_renderer(name: str, config: dict, **kwargs):
    if name not in _RENDERER_REGISTRY:
        raise ValueError(
            f"Unknown renderer: {name}. Available: {list(_RENDERER_REGISTRY.keys())}"
        )
    return _RENDERER_REGISTRY[name](config, **kwargs)
