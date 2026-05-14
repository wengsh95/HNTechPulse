#!/usr/bin/env bash
# TS/Remotion quality gate — run all checks and report results.
#
# Usage:
#   bash scripts/ts_quality_check.sh            # run all checks
#   bash scripts/ts_quality_check.sh --fix      # auto-fix where possible
#   bash scripts/ts_quality_check.sh --skip knip,audit  # skip specific checks

set -euo pipefail

REOTION_DIR="$(cd "$(dirname "$0")/.." && pwd)/src/providers/renderer/remotion"
cd "$REOTION_DIR"

FIX=false
SKIP=""

# Parse args
for arg in "$@"; do
  case "$arg" in
    --fix)   FIX=true ;;
    --skip)  shift; SKIP="${1:-}" ;;
    --skip=*) SKIP="${arg#--skip=}" ;;
  esac
done

SKIP_SET=$(echo "$SKIP" | tr ',' '\n' | sed '/^$/d')

should_skip() {
  echo "$SKIP_SET" | grep -qx "$1"
}

PASS=0
FAIL=0
FIXABLE=0

run_check() {
  local name="$1"
  local cmd="$2"
  local fixable="${3:-false}"

  if should_skip "$name"; then
    echo "  $name... SKIP"
    return
  fi

  echo "  $name..." >&2

  if output=$(eval "$cmd" 2>&1); then
    echo "  $name... OK"
    ((PASS++)) || true
  else
    echo "  $name... FAIL"
    echo "$output" | sed 's/^/    /'
    ((FAIL++)) || true
    if [ "$fixable" = "true" ]; then
      ((FIXABLE++)) || true
    fi
  fi
}

# ── Prettier ────────────────────────────────────────────────────────────────
if [ "$FIX" = true ]; then
  run_check "prettier" "npx prettier --write 'src/**/*.{ts,tsx,js,jsx,json,css,md}'" "true"
else
  run_check "prettier" "npx prettier --check 'src/**/*.{ts,tsx,js,jsx,json,css,md}'" "true"
fi

# ── ESLint ──────────────────────────────────────────────────────────────────
if [ "$FIX" = true ]; then
  run_check "eslint" "npx eslint --fix 'src/**/*.{ts,tsx}'" "true"
else
  run_check "eslint" "npx eslint 'src/**/*.{ts,tsx}'" "true"
fi

# ── TypeScript type check ──────────────────────────────────────────────────
run_check "tsc" "npx tsc --noEmit" "false"

# ── Vitest ─────────────────────────────────────────────────────────────────
run_check "vitest" "npx vitest run --reporter=verbose" "false"

# ── Knip (dead code) ──────────────────────────────────────────────────────
run_check "knip" "npx knip --no-exit-code" "false"

# ── npm audit ─────────────────────────────────────────────────────────────
run_check "audit" "npm audit --audit-level=moderate" "false"

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FIXABLE" -gt 0 ]; then
  echo "  ($FIXABLE fixable with --fix)"
fi

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
