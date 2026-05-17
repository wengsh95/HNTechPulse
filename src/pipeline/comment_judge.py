from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.interfaces import LLMProvider
from src.core.models import ContentPackage
from src.pipeline.comment_judgement import (
    comment_judgement_key,
    heuristic_story_judgement,
    load_comment_judgements,
    normalize_story_judgement,
    save_comment_judgements,
)
from src.utils.logger import setup_logger


class CommentJudge:
    def __init__(
        self,
        llm_provider: LLMProvider,
        config: dict,
        comment_analyzer=None,
        debug: bool = False,
    ):
        self.llm_provider = llm_provider
        self.config = config
        self.comment_analyzer = comment_analyzer
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("comment_judge_enabled", True)
        self.max_workers = int(analyze_cfg.get("comment_judge_max_workers", 2) or 1)
        self.fallback_on_error = analyze_cfg.get(
            "comment_judge_fallback_on_error", True
        )
        self.prompt_template_path = analyze_cfg.get(
            "comment_judge_prompt",
            "prompts/comment_analyze.md",
        )
        self.judge_candidate_count = analyze_cfg.get("max_comments_for_judge", 15)
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    def judge(self, content: ContentPackage, date: str) -> dict:
        if not self.enabled:
            self.logger.info("Comment judge disabled, using heuristic candidates")
            stories = {
                comment_judgement_key(item): heuristic_story_judgement(item)
                for item in content.items
            }
            save_comment_judgements(date, stories)
            return stories

        stories = load_comment_judgements(date)
        cached_count = 0
        for idx, item in enumerate(content.items):
            if comment_judgement_key(item) in stories:
                cached_count += 1
                self.logger.info(
                    f"  [{idx + 1}/{len(content.items)}] comment judge cached: "
                    f"{item.source_id} {item.title[:80]}"
                )
        missing = [
            (idx, item)
            for idx, item in enumerate(content.items)
            if comment_judgement_key(item) not in stories
        ]
        if not missing:
            self.logger.info(
                f"Loading comment judgements from cache: data/{date}/comment_judgement.json"
            )
            return stories

        self.logger.info(
            f"Judging comments for {len(missing)} stories "
            f"({cached_count} cached, total={len(content.items)})..."
        )
        workers = max(1, min(self.max_workers, len(missing)))

        def judge_one(idx_item):
            idx, item = idx_item
            label = (
                f"[{idx + 1}/{len(content.items)}] {item.source_id} {item.title[:80]}"
            )
            if not item.comments:
                self.logger.info(f"  {label}: no comments, using heuristic fallback")
                return comment_judgement_key(item), heuristic_story_judgement(item)
            try:
                # Use comment_analyzer to pre-filter candidates when available
                pre_filtered = None
                if self.comment_analyzer:
                    if hasattr(self.comment_analyzer, "get_judge_candidates"):
                        pre_filtered = self.comment_analyzer.get_judge_candidates(
                            item, n=self.judge_candidate_count
                        )
                    else:
                        pre_filtered = self.comment_analyzer.get_top_comments(
                            item, n=self.judge_candidate_count
                        )
                self.logger.info(
                    f"  {label}: judging {len(pre_filtered or item.comments)} comments "
                    f"(model request starting)"
                )
                result = self.llm_provider.judge_story_comments(
                    item,
                    idx,
                    self.prompt_template_path,
                    candidates=pre_filtered,
                )
                normalized = normalize_story_judgement(result, item)
                candidate_count = len(normalized.get("quote_candidates", []) or [])
                rejected_count = len(normalized.get("rejected", []) or [])
                self.logger.info(
                    f"  {label}: done, candidates={candidate_count}, rejected={rejected_count}"
                )
                return comment_judgement_key(item), normalized
            except Exception as e:
                if not self.fallback_on_error:
                    self.logger.error(f"  {label}: comment judge failed: {e}")
                    raise
                self.logger.warning(
                    f"  {label}: comment judge failed, using heuristic fallback: {e}"
                )
                fallback = heuristic_story_judgement(item)
                self.logger.info(
                    f"  {label}: fallback candidates="
                    f"{len(fallback.get('quote_candidates', []) or [])}"
                )
                return comment_judgement_key(item), fallback

        if workers == 1:
            for idx_item in missing:
                key, judgement = judge_one(idx_item)
                stories[key] = judgement
                save_comment_judgements(date, stories)
                self.logger.info(
                    f"  Saved comment judgement checkpoint: "
                    f"{len(stories)}/{len(content.items)} stories"
                )
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(judge_one, idx_item): idx_item
                    for idx_item in missing
                }
                for future in as_completed(futures):
                    key, judgement = future.result()
                    stories[key] = judgement
                    save_comment_judgements(date, stories)
                    self.logger.info(
                        f"  Saved comment judgement checkpoint: "
                        f"{len(stories)}/{len(content.items)} stories"
                    )

        save_comment_judgements(date, stories)
        self.logger.info(f"Saved comment judgements for {len(stories)} stories")
        return stories
