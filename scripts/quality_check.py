#!/usr/bin/env python3
"""Code quality gate — run all checks and report results.

Usage:
    uv run python scripts/quality_check.py          # run all checks
    uv run python scripts/quality_check.py --fix     # auto-fix where possible
    uv run python scripts/quality_check.py --skip mypy,pip-audit  # skip specific checks
"""

import argparse
import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"

# Windows console encoding fix
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)
sys.stderr = io.TextIOWrapper(
    sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    output: str = ""
    fixable: bool = False


def run(cmd: list[str], *, label: str, fixable: bool = False) -> CheckResult:
    try:
        r = subprocess.run(
            cmd, capture_output=True, cwd=str(ROOT), encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        return CheckResult(label, ok=False, output=f"command not found: {cmd[0]}")
    output = ((r.stdout or "") + (r.stderr or "")).strip()
    return CheckResult(label, ok=r.returncode == 0, output=output, fixable=fixable)


# ── Individual checks ──────────────────────────────────────────────────────


def check_ruff(fix: bool) -> CheckResult:
    cmd = [
        "uv",
        "run",
        "ruff",
        "check",
        str(SRC),
        str(TESTS),
        "--extend-ignore",
        "E402",
    ]
    if fix:
        cmd += ["--fix", "--unsafe-fixes"]
    return run(cmd, label="ruff", fixable=True)


def check_ruff_format(fix: bool) -> CheckResult:
    cmd = ["uv", "run", "ruff", "format", "--check", str(SRC), str(TESTS)]
    if fix:
        cmd = ["uv", "run", "ruff", "format", str(SRC), str(TESTS)]
    return run(cmd, label="ruff-format", fixable=True)


def check_vulture() -> CheckResult:
    return run(
        ["uv", "run", "vulture", str(SRC), "--min-confidence", "80"],
        label="vulture",
    )


def check_mypy() -> CheckResult:
    return run(
        [
            "uv",
            "run",
            "mypy",
            str(SRC),
            "--ignore-missing-imports",
            "--no-error-summary",
        ],
        label="mypy",
    )


def check_pytest() -> CheckResult:
    return run(
        ["uv", "run", "python", "-m", "pytest", str(TESTS), "-q", "--tb=short"],
        label="pytest",
    )


def check_coverage() -> CheckResult:
    return run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "coverage",
            "run",
            "-m",
            "pytest",
            str(TESTS),
            "-q",
            "--tb=short",
        ],
        label="coverage-run",
    )


def check_coverage_report() -> CheckResult:
    return run(
        ["uv", "run", "python", "-m", "coverage", "report", "--fail-under=50"],
        label="coverage-report",
    )


def check_pip_audit() -> CheckResult:
    return run(
        ["uv", "run", "pip-audit", "--desc"],
        label="pip-audit",
    )


def check_pre_commit(fix: bool) -> CheckResult:
    cmd = ["uv", "run", "pre-commit", "run", "--all-files"]
    return run(cmd, label="pre-commit", fixable=True)


# ── Runner ─────────────────────────────────────────────────────────────────

ALL_CHECKS = [
    ("ruff", lambda fix, skip: check_ruff(fix)),
    ("ruff-format", lambda fix, skip: check_ruff_format(fix)),
    ("vulture", lambda fix, skip: check_vulture()),
    ("mypy", lambda fix, skip: check_mypy()),
    ("pytest", lambda fix, skip: check_pytest()),
    (
        "coverage",
        lambda fix, skip: (
            check_coverage()
            if not skip
            else CheckResult("coverage", ok=True, output="skipped")
        ),
    ),
    (
        "coverage-report",
        lambda fix, skip: (
            check_coverage_report()
            if not skip
            else CheckResult("coverage-report", ok=True, output="skipped")
        ),
    ),
    ("pip-audit", lambda fix, skip: check_pip_audit()),
    ("pre-commit", lambda fix, skip: check_pre_commit(fix)),
]


def main():
    parser = argparse.ArgumentParser(description="Code quality gate")
    parser.add_argument("--fix", action="store_true", help="auto-fix where possible")
    parser.add_argument("--skip", default="", help="comma-separated checks to skip")
    args = parser.parse_args()

    skip = set(s.strip() for s in args.skip.split(",") if s.strip())
    results: list[CheckResult] = []

    for name, fn in ALL_CHECKS:
        if name in skip:
            results.append(CheckResult(name, ok=True, output="skipped"))
            continue
        is_skipped = "coverage" in skip and name == "coverage-report"
        print(f"  {name}...", end=" ", flush=True)
        r = fn(args.fix, is_skipped)
        results.append(r)
        tag = "OK" if r.ok else "FAIL"
        print(tag)
        if not r.ok and r.output:
            for line in r.output.splitlines():
                print(f"    {line}")

    print()
    ok_count = sum(r.ok for r in results)
    fail_count = len(results) - ok_count
    fixable_count = sum(r.fixable and not r.ok for r in results)

    print(f"Results: {ok_count} passed, {fail_count} failed")
    if fixable_count:
        print(f"  ({fixable_count} fixable with --fix)")

    if fail_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
