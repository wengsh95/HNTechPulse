# ADR-005: Publishing-copy policy is a standalone module

**Status**: Accepted (2026-09)

## Context

`src/pipeline/stages/title_cover.py` grew to 793 lines mixing three
responsibilities: the publishing-copy policy (title/description/tags/cover-copy
validation, grounding, description cleaning, uncertainty preservation), the
title LLM orchestration, and the cover image + props rendering.  The copy
policy was ~360 lines of pure functions plus a handful of module constants,
deeply coupled to each other but with no production consumer outside the file.

## Decision

Extract the copy policy into `src/pipeline/publish_copy.py` — a module of pure
functions (`_clean_publish_description`, `_downgrade_unsupported_publish_claims`,
`_validate_title_payload`, `_validate_title_grounding`, the cover-variant and
uncertainty helpers, `_ensure_all_stories_in_description`) plus
`COVER_VARIANT_COUNT` and `TITLE_NORMALIZATION_VERSION`.  The move is
byte-for-byte; no copy rule changed.  `title_cover.py` keeps only orchestration
(the LLM call, cache handling, image generation, props rendering) and
`_normalize_cover_prompt`, which is image-prompt policy, not copy.

`COVER_VARIANT_COUNT` moves with the policy (it is the copy-variant contract)
and is now imported by the packaging and title/cover stages instead of being a
local packaging constant — the `src/pipeline/publish_copy` → `stages` import
direction would have been a sub-package dependency, so the constant's home is
the policy module.

## Consequences

- The stage module is ~433 lines of orchestration; the copy policy can be
  reviewed, tested, and reused on its own.
- Copy rules are pinned by `tests/test_title_cover_stage.py` (now importing
  from `publish_copy`), so a future copy change is a deliberate edit, not an
  accidental one.
- Deliberately left in the stage layer: `_build_focus_story_input` /
  `_extract_highlight_entries` (the stage mixin interface that prepares the
  title input) — input preparation is not copy policy.