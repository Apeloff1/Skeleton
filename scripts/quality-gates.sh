#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Toolchain contract ==\n'
python scripts/check_toolchain_contract.py

printf '\n== Skeleton core syntax ==\n'
python -m compileall -q skeleton

printf '\n== Backend syntax ==\n'
python -m compileall -q backend

printf '\n== Backend process safety ==\n'
python backend/scripts/check_process_safety.py

printf '\n== Backend execution boundary regressions ==\n'
python -m pytest -q --noconftest \
  backend/tests/test_exec_guard.py \
  backend/tests/test_process_safety_gate.py \
  backend/tests/test_process_safety_destructuring.py

if command -v yarn >/dev/null 2>&1; then
  printf '\n== Frontend lint ==\n'
  yarn --cwd frontend lint:ci

  printf '\n== Frontend typecheck ==\n'
  yarn --cwd frontend typecheck
else
  printf '\nERROR: yarn is required for frontend verification.\n' >&2
  exit 127
fi

printf '\nAll canonical quality gates passed.\n'
