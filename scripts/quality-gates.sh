#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

printf '\n== Toolchain contract ==\n'
python scripts/check_toolchain_contract.py

printf '\n== Provider runtime boundary ==\n'
python scripts/check_provider_runtime_boundary.py

printf '\n== Skeleton core syntax ==\n'
python -m compileall -q skeleton

printf '\n== Backend syntax ==\n'
python -m compileall -q backend

printf '\n== Runtime, cache, deployment, and observability contracts ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_model_runtime.py \
  tests/test_provider_runtime_boundary.py \
  tests/test_orchestration.py \
  tests/test_orchestration_error_redaction.py \
  tests/test_frontier_runtime_memory_retrieval.py \
  tests/test_agent_coordination.py \
  skeleton/testing/test_tiered_cache.py \
  skeleton/testing/test_deployment_security_defaults.py \
  skeleton/testing/test_frontier_observability_correlation.py \
  tests/test_observability.py

printf '\n== Backend process safety ==\n'
python backend/scripts/check_process_safety.py

printf '\n== Repository process safety ==\n'
python scripts/check_repository_process_safety.py

printf '\n== Backend unsafe deserialization safety ==\n'
python backend/scripts/check_deserialization_safety.py

printf '\n== Backend/frontend high-confidence SAST ==\n'
python backend/scripts/check_sast_security.py

printf '\n== Core/tooling Python high-confidence SAST ==\n'
python scripts/check_repository_python_sast.py

printf '\n== JavaScript child_process alias safety ==\n'
python backend/scripts/check_js_process_alias_safety.py

printf '\n== GitHub Actions workflow security ==\n'
python backend/scripts/check_workflow_security.py

printf '\n== Repository secret hygiene ==\n'
python backend/scripts/check_secret_hygiene.py

printf '\n== Repository malware / IOC scan ==\n'
python backend/scripts/check_malware_iocs.py

printf '\n== Backend security scanner regressions ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  backend/tests/test_exec_guard.py \
  backend/tests/test_process_safety_gate.py \
  backend/tests/test_process_safety_destructuring.py \
  backend/tests/test_process_safety_partial.py \
  backend/tests/test_process_safety_namespace_get.py \
  backend/tests/test_process_safety_getattribute.py \
  backend/tests/test_process_safety_helper_aliases.py \
  backend/tests/test_repository_process_safety.py \
  backend/tests/test_deserialization_safety_gate.py \
  backend/tests/test_sast_security_gate.py \
  backend/tests/test_repository_python_sast_scope.py \
  backend/tests/test_js_process_alias_safety.py \
  backend/tests/test_workflow_security_gate.py \
  backend/tests/test_secret_hygiene_gate.py \
  backend/tests/test_malware_ioc_gate.py \
  backend/tests/test_incident_response_runbook.py \
  backend/tests/test_webhook_cron_security.py \
  backend/tests/test_audit_framing_stack.py

if command -v yarn >/dev/null 2>&1; then
  printf '\n== Frontend lint ==\n'
  yarn --cwd frontend lint:ci

  printf '\n== Frontend typecheck ==\n'
  yarn --cwd frontend typecheck
else
  printf '\nERROR: yarn is required for frontend verification.\n' >&2
  exit 127
fi

printf '\nAll canonical quality and security gates passed.\n'