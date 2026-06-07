import re


_CJK_ALNUM_SPACE_PATTERNS = (
    (re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])"), ""),
    (re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[A-Za-z0-9])"), ""),
    (re.compile(r"(?<=[A-Za-z0-9])\s+(?=[\u4e00-\u9fff])"), ""),
)


def normalize_cjk_mixed_spacing(text: str) -> str:
    """Tighten stray spaces between CJK and ASCII words for CN-facing copy.

    Keeps spaces inside pure ASCII phrases such as ``Windows PC`` while removing
    awkward mixed-script gaps like ``AI 大厂`` -> ``AI大厂`` and
    ``造一颗 CPU`` -> ``造一颗CPU``.
    """

    normalized = text.strip()
    for pattern, replacement in _CJK_ALNUM_SPACE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    return normalized
