"""Comment analysis pipeline: scoring, selection, judging."""

from src.pipeline.comment.text import clean_comment_text, is_resource_pointer_comment
from src.pipeline.comment.scoring import (
    compute_comment_quality,
    compute_comment_relevance,
    compute_judge_candidate_score,
    local_comment_type_hints,
)
from src.pipeline.comment.selection import (
    classify_comment_stance,
    comment_key,
    is_quotable_comment,
    select_judge_candidate_comments,
    select_representative_comments,
    select_comments_by_ids,
    select_quote_comments,
)
from src.pipeline.comment.judge import (
    ANALYSIS_SCHEMA_VERSION,
    JUDGEMENT_SCHEMA_VERSION,
    DISCUSSION_MODES,
    COMMENT_LANES,
    CommentAnalyzer,
    CommentJudge,
    comment_judgement_key,
    normalize_story_judgement,
    load_comment_judgements,
    save_comment_judgements,
    candidate_ids_for_story,
)
from src.pipeline.comment.refiner import CommentRefiner

__all__ = [
    "clean_comment_text",
    "is_resource_pointer_comment",
    "compute_comment_quality",
    "compute_comment_relevance",
    "compute_judge_candidate_score",
    "local_comment_type_hints",
    "classify_comment_stance",
    "comment_key",
    "is_quotable_comment",
    "select_judge_candidate_comments",
    "select_representative_comments",
    "select_comments_by_ids",
    "select_quote_comments",
    "ANALYSIS_SCHEMA_VERSION",
    "JUDGEMENT_SCHEMA_VERSION",
    "DISCUSSION_MODES",
    "COMMENT_LANES",
    "CommentAnalyzer",
    "CommentJudge",
    "comment_judgement_key",
    "normalize_story_judgement",
    "load_comment_judgements",
    "save_comment_judgements",
    "candidate_ids_for_story",
    "CommentRefiner",
]
