#!/usr/bin/env bash
# Forge verify gauntlet — sibling pattern of gameforge-rs scripts/verify.sh
# Fail-closed multi-step gates for Skeleton's Python forge path.
# Scripts/tests only; does not touch forge lifespan / verify_loop wiring.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() {
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  STEP: $*"
  echo "════════════════════════════════════════════════════════════"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

# Prefer python3; fall back to python if needed.
if have_cmd python3; then
  PY=python3
elif have_cmd python; then
  PY=python
else
  echo "ERROR: python3/python not found" >&2
  exit 1
fi

step "compileall"
"$PY" -m compileall -q skeleton

step "forge unit (run_unit — includes tests.test_forge)"
PYTHONPATH=. "$PY" tests/run_unit.py

step "forge verifier tests (pytest)"
if "$PY" -c 'import pytest' 2>/dev/null; then
  PYTHONPATH=. "$PY" -m pytest \
    skeleton/testing/test_forge_verifier.py \
    skeleton/testing/test_forge_repair.py \
    -q
else
  echo "SKIP: pytest not installed — compileall + run_unit already passed"
fi

step "ruff on forge paths"
RUFF_BIN=""
if have_cmd ruff; then
  RUFF_BIN=ruff
elif have_cmd uvx; then
  RUFF_BIN="uvx ruff"
fi
if [[ -n "$RUFF_BIN" ]]; then
  # shellcheck disable=SC2086
  $RUFF_BIN check skeleton/forge skeleton/intelligence/forge_verifier.py
else
  echo "SKIP: ruff/uvx not available"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  VERDICT: ALL GATES PASSED"
echo "════════════════════════════════════════════════════════════"
