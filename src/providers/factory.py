from src.utils.logger import setup_logger


_FETCHER_REGISTRY: dict[str, type] = {}
_LLM_REGISTRY: dict[str, type] = {}

_logger = setup_logger(__name__)


def register_fetcher(name: str, cls):
    _FETCHER_REGISTRY[name] = cls


def register_llm(name: str, cls):
    _LLM_REGISTRY[name] = cls


def _auto_register():
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
