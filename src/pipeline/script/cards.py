"""Card normalization for story and atmosphere cards."""

from src.core.models import ContentItem, SceneElement, ScriptSegment
from src.pipeline.comment import (
    candidate_ids_for_story,
    classify_comment_stance,
    select_comments_by_ids,
)


def normalize_atmosphere_card(
    segment: ScriptSegment, item: ContentItem, judgement: dict
) -> None:
    """Inject debate_focus, stance_distribution, and selected_comment_ids from comment judgement into atmosphere_card props."""
    debate_focus = judgement.get("debate_focus") or []
    stance_distribution = judgement.get("stance_distribution") or {}

    for elem in segment.scene_elements:
        if elem.element_type != "atmosphere_card":
            continue
        props = dict(elem.props or {})
        if debate_focus:
            props["debate_focus"] = debate_focus
        if stance_distribution:
            props["stance_distribution"] = stance_distribution

        # Determine quote_cap based on stance diversity
        selected_ids = props.get("selected_comment_ids") or []
        comments_by_id = {
            str(c.source_id): c for c in item.comments if c.source_id is not None
        }
        preselected_stances = {
            classify_comment_stance(comments_by_id[str(cid)])
            for cid in selected_ids
            if str(cid) in comments_by_id
        }
        quote_cap = 2
        if stance_distribution:
            dominant_stance, dominant_share = max(
                stance_distribution.items(), key=lambda x: x[1]
            )
            if dominant_share >= 0.6 and dominant_stance not in preselected_stances:
                quote_cap = 3

        # Trust LLM ordering: take top candidates directly by ID
        preferred_ids = candidate_ids_for_story(judgement, max_n=quote_cap + 2)
        combined_ids = list(selected_ids)
        for comment_id in preferred_ids:
            if comment_id not in combined_ids:
                combined_ids.append(comment_id)

        selected_comments = select_comments_by_ids(
            item.comments, combined_ids, max_n=quote_cap
        )

        props["selected_comment_ids"] = [
            str(c.source_id) for c in selected_comments if c.source_id is not None
        ]

        elem.props = props


def normalize_story_cards(
    segment: ScriptSegment, item: ContentItem, judgement: dict
) -> None:
    """Inject common story metadata into all visual story card variants."""
    assert item.editor_angle, f"Story {item.source_id} missing editor_angle"
    assert item.title_cn, f"Story {item.source_id} missing title_cn"

    for elem in segment.scene_elements:
        if elem.element_type not in {
            "event_card",
            "atmosphere_card",
        }:
            continue
        props = dict(elem.props or {})
        props.setdefault("source_title", item.title)
        props.setdefault("title_cn", item.title_cn)
        props.setdefault("editor_angle", item.editor_angle)
        if item.key_points:
            props.setdefault("key_points", item.key_points)
        if item.keywords:
            props.setdefault("keywords", item.keywords)
        if item.category:
            props.setdefault("category", item.category)
        if item.why_it_matters:
            props.setdefault("why_it_matters", item.why_it_matters)
        if item.score is not None:
            props.setdefault("score", item.score)
        if item.comment_count is not None:
            props.setdefault("comment_count", item.comment_count)
        if judgement:
            props.setdefault("discussion_mode", judgement.get("discussion_mode", ""))
            props.setdefault(
                "discussion_summary", judgement.get("discussion_summary", "")
            )
        elem.props = props


def coerce_card_narrations_for_mode(segment: ScriptSegment, mode: str) -> None:
    """Keep LLM output within the configured tier shape."""
    expected = ["event_card", "atmosphere_card"]

    card_narrations = segment.meta.get("card_narrations", []) or []
    filtered = [card for card in card_narrations if card.get("card_type") in expected]
    if filtered:
        segment.meta["card_narrations"] = filtered

    segment.scene_elements = [
        elem for elem in segment.scene_elements if elem.element_type in expected
    ]
    story_index = segment.meta.get("story_index")
    for elem in segment.scene_elements:
        if story_index is not None:
            break
        if elem.props.get("story_index") is not None:
            story_index = elem.props.get("story_index")
            break
    if story_index is None:
        story_index = segment.meta.get("story_index", 0)

    existing = set()
    for elem in segment.scene_elements:
        existing.add(elem.element_type)
        props = dict(elem.props or {})
        props["story_index"] = story_index
        elem.props = props

    for card_type in expected:
        if card_type not in existing:
            segment.scene_elements.append(
                SceneElement(
                    element_type=card_type,
                    start_time=0.0,
                    end_time=5.0,
                    props={"story_index": story_index},
                )
            )


def split_long_subtitle(text: str, max_cjk: int = 36, max_chars: int = 70) -> list[str]:
    """Split a single subtitle into 1-2 cues when it exceeds the readable width."""
    cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
    ascii_count = len(text) - cjk_count
    weight = cjk_count + ascii_count / 2
    if weight <= max_cjk and len(text) <= max_chars:
        return [text]

    breakers = "，。；：、!?！？,;"
    midpoint = len(text) // 2
    best_idx = -1
    best_dist = len(text)
    for i, ch in enumerate(text):
        if ch in breakers:
            dist = abs(i - midpoint)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
    if best_idx <= 0 or best_idx >= len(text) - 1:
        return [text]
    left = text[: best_idx + 1].rstrip(breakers + " ").strip()
    right = text[best_idx + 1 :].lstrip(breakers + " ").strip()
    if not left or not right:
        return [text]
    return [left, right]


_CLOSING_PUNCT = set("。！？.!?：:；;")


def _ensure_punctuation(text: str) -> str:
    """Append 。 if the subtitle doesn't end with closing punctuation."""
    if text and text[-1] not in _CLOSING_PUNCT:
        return text + "。"
    return text


def extract_subtitle_texts(card: dict) -> list[str]:
    raw_texts = card.get("subtitle_texts", []) or []
    return [
        _ensure_punctuation(piece)
        for t in raw_texts
        if t and t.strip()
        for piece in split_long_subtitle(t.strip())
    ]
