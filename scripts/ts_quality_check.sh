#!/usr/bin/env bash
# TypeScript code quality gate — run all checks and report results.
#
# Usage:
#     bash scripts/ts_quality_check.sh          # run all checks
#     bash scripts/ts_quality_check.sh --fix    # auto-fix where possible

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../src/providers/renderer/remotion" && pwd)"
cd "$PROJECT_DIR"

FIX=false
for arg in "$@"; do
  case "$arg" in
    --fix) FIX=true ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

# ── Individual checks ──────────────────────────────────────────────────────

run_check() {
  local name="$1"
  shift
  printf "  %-12s ... " "$name"
  local out
  if out=$("$@" 2>&1); then
    echo "OK"
    return 0
  else
    echo "FAIL"
    if [ -n "$out" ]; then
      echo "$out" | sed 's/^/    /'
    fi
    return 1
  fi
}

# ── Runner ─────────────────────────────────────────────────────────────────

declare -a NAMES=()
declare -a OKS=()
declare -a FIXABLE=()

run() {
  local name="$1"
  local fixable="$2"
  shift 2
  if run_check "$name" "$@"; then
    NAMES+=("$name"); OKS+=("1"); FIXABLE+=("$fixable")
  else
    NAMES+=("$name"); OKS+=("0"); FIXABLE+=("$fixable")
  fi
}

if $FIX; then
  run "lint"        true  npm run lint:fix
  run "format"      true  npm run format
else
  run "lint"        true  npm run lint
  run "format"      true  npm run format:check
fi

run "typecheck"   false npm run typecheck
if ls src/**/*.test.* >/dev/null 2>&1 || find src -name "*.test.ts" -o -name "*.test.tsx" 2>/dev/null | grep -q .; then
  run "test"        false npm run test
else
  printf "  %-12s ... SKIPPED (no test files)\n" "test"
  NAMES+=("test"); OKS+=("1"); FIXABLE+=("false")
fi
run "knip"        false npm run knip
run "audit"       false npm run audit

# ── Summary ────────────────────────────────────────────────────────────────

echo
PASS=0
FAIL=0
FIXABLE_COUNT=0
for i in "${!NAMES[@]}"; do
  if [ "${OKS[$i]}" = "1" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    [ "${FIXABLE[$i]}" = "true" ] && FIXABLE_COUNT=$((FIXABLE_COUNT + 1))
  fi
done

echo "Results: $PASS passed, $FAIL failed"
if [ $FIXABLE_COUNT -gt 0 ]; then
  echo "  ($FIXABLE_COUNT fixable with --fix)"
fi

[ $FAIL -eq 0 ]
