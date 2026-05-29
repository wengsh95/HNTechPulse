"""Text cleaning utilities for comment processing."""

import html
import re


_HTML_TAG_RE = re.compile(r"<[^>]*>")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"```|`[^`]+`")
_STRUCTURED_RE = re.compile(r"^\s*[-*>]\s", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]+")
_RESOURCE_POINTER_RE = re.compile(
    r"\b("
    r"here(?:'s| is)|there(?:'s| is)|see also|related|link|article|paper|blog post|"
    r"write-?up|documentation|docs|guide|tutorial|resource|read this|check out|"
    r"worth reading|may be useful|might be useful"
    r")\b",
    re.IGNORECASE,
)
_VIEWPOINT_MARKER_RE = re.compile(
    r"\b("
    r"because|since|therefore|however|but|although|unless|if|when|why|how|"
    r"should|shouldn't|cannot|can't|won't|would|could|problem|trade-?off|risk|"
    r"concern|worried|skeptical|convinced|agree|disagree|prefer|instead|actually|"
    r"experience|used|tried|built|maintain|production|fails?|breaks?|works?|"
    r"means|implies|depends"
    r")\b",
    re.IGNORECASE,
)


def clean_comment_text(text: str) -> str:
    """Strip HN HTML and normalize whitespace for scoring, translation, and display."""
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_resource_pointer_comment(text: str) -> bool:
    """Return True for link/resource pointers that do not carry a viewpoint."""
    clean_text = clean_comment_text(text)
    if not clean_text or not _URL_RE.search(clean_text):
        return False

    without_urls = _URL_RE.sub("", clean_text).strip(" :-.,;()[]{}<>")
    word_count = len(_WORD_RE.findall(without_urls))
    has_pointer_language = bool(_RESOURCE_POINTER_RE.search(without_urls))
    has_viewpoint_language = bool(_VIEWPOINT_MARKER_RE.search(without_urls))

    if len(without_urls) < 30:
        return True
    if len(without_urls) < 90 and has_pointer_language and not has_viewpoint_language:
        return True
    if word_count <= 14 and has_pointer_language and not has_viewpoint_language:
        return True
    return False
