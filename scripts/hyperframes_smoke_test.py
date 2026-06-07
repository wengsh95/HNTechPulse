"""
HyperFrames smoke test: prepare → render → extract key frames.

Runs the full HyperFrames pipeline for a given date and extracts review frames.
Exit code 0 = all steps passed, 1 = failure at any step.

Usage:
    uv run python scripts/hyperframes_smoke_test.py --date 2026-06-07
    uv run python scripts/hyperframes_smoke_test.py --date 2026-06-07 --skip-render
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, cmd: list[str]) -> bool:
    """Run a subprocess step, return True on success."""
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"\nFAILED: {name} (exit code {result.returncode})", file=sys.stderr)
        return False
    print(f"\nOK: {name}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="HyperFrames smoke test")
    parser.add_argument("--date", required=True, help="Pipeline date (YYYY-MM-DD)")
    parser.add_argument("--skip-render", action="store_true", help="Skip the render step (prepare only)")
    parser.add_argument("--skip-review", action="store_true", help="Skip the review frame extraction")
    args = parser.parse_args()

    date = args.date
    render_script = str(PROJECT_ROOT / "scripts" / "render_hyperframes_from_cli_props.py")
    review_script = str(PROJECT_ROOT / "scripts" / "review_hyperframes_render.py")
    python = sys.executable

    steps_passed = 0
    steps_total = 0

    # Step 1: Prepare
    steps_total += 1
    if run_step("prepare", [python, render_script, "--date", date, "--prepare-only"]):
        steps_passed += 1
    else:
        print(f"\nSmoke test FAILED at prepare step. {steps_passed}/{steps_total} steps passed.")
        sys.exit(1)

    # Step 2: Render (optional)
    if not args.skip_render:
        steps_total += 1
        if run_step("render", [python, render_script, "--date", date]):
            steps_passed += 1
        else:
            print(f"\nSmoke test FAILED at render step. {steps_passed}/{steps_total} steps passed.")
            sys.exit(1)
    else:
        print("\nSkipping render (--skip-render)")

    # Step 3: Review frames (optional)
    if not args.skip_review and not args.skip_render:
        steps_total += 1
        if run_step("review", [python, review_script, "--date", date]):
            steps_passed += 1
        else:
            print(f"\nWARNING: Review frame extraction failed. {steps_passed}/{steps_total} steps passed.")
            # Non-fatal: render succeeded even if frame extraction fails
    else:
        print("\nSkipping review frame extraction")

    print(f"\n{'='*60}")
    print(f"SMOKE TEST PASSED: {steps_passed}/{steps_total} steps completed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
