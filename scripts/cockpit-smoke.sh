#!/usr/bin/env bash
# Forge cockpit smoke gauntlet — Skeleton Python CLI baseline.
#
# Sibling pattern of Apeloff1/hyperforge-cockpit-sota:
#   scripts/browser-smoke.mjs
#   scripts/browser-smoke-verdict.mjs
#   scripts/brand-check.mjs
#   scripts/qa-flight.mjs
# Fail-closed step/verdict style adapted to Skeleton's GameForge CI gates
# (eras / plan / cockpit blend / walk). Complements scripts/verify-forge.sh
# (PR #9) without stomping Lana spine (#7) or Glenny circular-import (#8).
#
# Scripts/tests only — does not touch api/server.py, lifespan,
# skeleton/forge/universal.py, verify_loop, or repair wiring.
#
# Hard gates: compileall + python -m skeleton eras|plan|cockpit|walk.
# Intentionally omits the CI unit runner: on origin/main that path
# (and often the CLI import itself) hits the known PipelineVerifier
# circular import (Glenny/#8). Fix that on #8; this gauntlet stays extend-only.
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

export PYTHONPATH="${PYTHONPATH:-.}"

step "compileall skeleton"
"$PY" -m compileall -q skeleton

# Same command set as .github/workflows/ci.yml "Skeleton GameForge" job.
step "eras"
"$PY" -m skeleton eras

step "plan"
"$PY" -m skeleton plan "soulslike extraction with bonfire rest"

step "cockpit blend"
"$PY" -m skeleton cockpit "BLEND ERA arcade_golden_age soulslike 0.5"

step "walk --era soulslike"
"$PY" -m skeleton walk --era soulslike

step "cockpit smoke meta-test (optional pytest)"
if "$PY" -c 'import pytest' 2>/dev/null; then
  PYTHONPATH=. "$PY" -m pytest \
    skeleton/testing/test_cockpit_smoke_gauntlet.py \
    -q
else
  echo "SKIP: pytest not installed — hard gates already exercised"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  VERDICT: ALL GATES PASSED"
echo "════════════════════════════════════════════════════════════"
