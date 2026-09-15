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

printf '\n== Provider runtime and agent orchestration contracts ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_model_runtime.py \
  tests/test_orchestration.py \
  tests/test_orchestration_error_redaction.py \
  tests/test_agent_coordination.py

printf '\n== Backend process safety ==\n'
python backend/scripts/check_process_safety.py

printf '\n== Repository process safety ==\n'
python scripts/check_repository_process_safety.py

printf '\n== Backend unsafe deserialization safety ==\n'
python backend/scripts/check_deserialization_safety.py

printf '\n== Repository high-confidence SAST ==\n'
python backend/scripts/check_sast_security.py

printf '\n== JavaScript child_process alias safety ==\n'
python backend/scripts/check_js_process_alias_safety.py

printf '\n== GitHub Actions workflow security ==\n'
python backend/scripts/check_workflow_security.py

printf '\n== Workflow input shell-boundary security ==\n'
python backend/scripts/check_workflow_input_security.py

printf '\n== Repository secret hygiene ==\n'
python backend/scripts/check_secret_hygiene.py

printf '\n== Repository malware/IOC safety ==\n'
python backend/scripts/check_malware_iocs.py

printf '\n== Quality gate complete ==\n'
