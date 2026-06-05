# Archive — One-off Debug Scripts

These scripts are preserved for historical reference but should NOT be used directly.
They were created during specific debugging sessions and contain **hardcoded dates
and source IDs** that are no longer valid.

## Files

- `check_content.py` — Inspect enrichment status of two specific items (`48295679`, `48293080`) on date `2026-05-28`
- `fix_content.py` — Force-mark those same items as `downloaded_page` in `content.json`
- `force_continue.py` — Manually continue past failed enrichment (legacy `brief_indices` filter)
- `remove_failed.py` — Same content-mutation pattern as `fix_content.py`
- `remove_failed_items.py` — Remove failed items from `brief_indices` (pre-2026 schema)

## Why Archived

These were written to recover from a specific failed run on `2026-05-28`. The
HN `source_id` values (48295679, 48293080) are ephemeral and not meaningful
to future runs. Re-running them today would either:
- Open a non-existent `data/2026-05-28/content.json` (FileNotFoundError)
- Silently mutate the wrong day's content if a path was hardcoded to today

## Replacements

If you need similar debugging in the future, prefer:
- `data/{date}/report.md` — auto-generated run report (issue summary)
- `data/{date}/downloaded_pages/{source_id}.html` — manual download directory
- `scripts/quality_check.py` — code quality gate

The pipeline's "failed items" guidance in [orchestrator.py:353-368](../pipeline/orchestrator.py)
is the supported flow for resuming after manual page downloads.
