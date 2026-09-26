#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Plugin autoload is intentionally disabled in isolated test commands below.
# Explicitly load the approved asyncio plugin so async tests remain hermetic.
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }-p pytest_asyncio.plugin"

printf '\n== Toolchain contract ==\n'
python scripts/check_toolchain_contract.py

printf '\n== Canonical local/CI quality parity ==\n'
python scripts/check_quality_gate_parity.py

printf '\n== Provider runtime boundary ==\n'
python scripts/check_provider_runtime_boundary.py
python scripts/check_provider_bootstrap.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_provider_contract.py \
  skeleton/testing/test_provider_surface_inventory.py

printf '\n== Provider capability matrix ==\n'
python scripts/check_provider_capability_matrix.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_provider_capability_matrix.py

printf '\n== Architecture boundaries ==\n'
python scripts/check_architecture_boundaries.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_architecture_boundaries.py

printf '\n== AI master plan ==\n'
python scripts/check_ai_master_plan.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_master_plan.py

printf '\n== AI edge/historical catalogue ==\n'
python scripts/check_ai_edge_case_catalog.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_edge_case_catalog.py

printf '\n== AI exotic systems catalogue ==\n'
python scripts/check_ai_exotic_systems_catalog.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_exotic_systems_catalog.py

printf '\n== P0 edge-case construction matrix ==\n'
python scripts/check_ai_p0_edge_case_matrix.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_p0_edge_case_matrix.py

printf '\n== Full edge-case construction matrix ==\n'
python scripts/check_ai_full_edge_case_matrix.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_full_edge_case_matrix.py

printf '\n== Master build sequence ==\n'
python scripts/check_ai_master_build_sequence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_master_build_sequence.py

printf '\n== Canonical AI file tree ==\n'
python scripts/check_ai_file_tree.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_file_tree.py

printf '\n== Masterplan engineering pass ==\n'
python scripts/check_ai_engineering_pass.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_engineering_pass.py

printf '\n== AIQ engineering propagation ==\n'
python scripts/check_ai_engineering_task_matrix.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_engineering_task_matrix.py

printf '\n== Signed build accountability ==\n'
python scripts/check_ai_build_accountability.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_ai_build_accountability.py \
  skeleton/testing/test_ai_accountability_cli.py

printf '\n== Governance lifecycle accountability ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_data_governance.py \
  skeleton/testing/test_data_lifecycle.py \
  skeleton/testing/test_governance_registry.py \
  skeleton/testing/test_lifecycle_adapters.py \
  skeleton/testing/test_governance_audit.py

printf '\n== RAG state authority convergence ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$ROOT/backend:$ROOT${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q --noconftest \
  backend/tests/test_rag_state_repository.py \
  backend/tests/test_rag_state_authority.py

printf '\n== Durable tenant quota persistence ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_tenant_quota.py \
  skeleton/testing/test_tenant_quota_sqlite.py \
  skeleton/testing/test_admission_runtime.py \
  skeleton/testing/test_actual_usage_metering.py \
  skeleton/testing/test_shared_pressure.py

printf '\n== Authoritative-first recovery contract ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_state_recovery_drill.py

printf '\n== Durable operation authority and outbox ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_operation_contract.py \
  skeleton/testing/test_operation_store.py \
  skeleton/testing/test_operation_runtime.py \
  skeleton/testing/test_operation_server_binding.py \
  skeleton/testing/test_operation_stream.py \
  skeleton/testing/test_operation_stream_store.py

printf '\n== Skeleton core syntax ==\n'
python -m compileall -q skeleton

printf '\n== Shell execution plane regressions ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_shell_*.py

printf '\n== Shell worker runtime regressions ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_worker_*.py

printf '\n== Backend Ruff ==\n'
(
  cd backend
  python -m ruff check . --output-format=github
)

printf '\n== Backend syntax ==\n'
python -m compileall -q backend

printf '\n== Provider timeout/failure chaos ==\n'
(
  cd backend
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    python -m pytest -q --noconftest \
    tests/test_ai_provider_reliability.py
)

printf '\n== Runtime, adversarial, cache, deployment, API, and observability contracts ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_model_runtime.py \
  tests/test_adversarial_engine.py \
  tests/test_adversarial_judge_isolation.py \
  tests/test_tri_adversarial_engine.py \
  skeleton/testing/test_provider_stream_reliability_profiles.py \
  tests/test_provider_runtime_boundary.py \
  tests/test_orchestration.py \
  tests/test_generated_code_sandbox.py \
  skeleton/testing/test_scanner_integrity.py \
  skeleton/testing/test_defense_plane.py \
  skeleton/testing/test_defense_control_plane_contract.py \
  skeleton/testing/test_incident_containment.py \
  skeleton/testing/test_automation_control_plane.py \
  skeleton/testing/test_pr_automation_event_firewall.py \
  skeleton/testing/test_pr_automation_operator_safety.py \
  skeleton/testing/test_outbound_url_resolution_security.py \
  skeleton/testing/test_security_rooted_fs.py \
  skeleton/testing/test_security_archive_sandbox.py \
  skeleton/testing/test_security_outbound_http.py \
  tests/test_container_digest_refresh.py \
  tests/test_container_digest_refresh_workflow.py \
  tests/test_orchestration_error_redaction.py \
  tests/test_frontier_runtime_memory_retrieval.py \
  tests/test_retrieval_pipeline_internals.py \
  tests/test_quad_retrieval_internals.py \
  tests/test_agent_coordination.py \
  tests/test_api_gateway_rate_limit_reliability.py \
  tests/test_middleware_rate_limiter.py \
  tests/test_api_gateway_payload_reliability.py \
  tests/test_api_gateway_error_redaction.py \
  tests/test_webhook_destination_security.py \
  skeleton/testing/test_tiered_cache.py \
  skeleton/testing/test_retrieval_hot_path.py \
  skeleton/testing/test_orchestration_reliability_profiles.py \
  skeleton/testing/test_state_reliability_profiles.py \
  skeleton/testing/test_api_gateway_reliability_profiles.py \
  skeleton/testing/test_process_resource_reliability_profiles.py \
  skeleton/testing/test_deployment_security_defaults.py \
  skeleton/testing/test_repo_intelligence_git_index.py \
  skeleton/testing/test_frontier_observability_correlation.py \
  skeleton/testing/test_current_main_observability_closure.py \
  skeleton/testing/test_request_seal_id_validation.py \
  tests/test_observability.py \
  tests/test_runtime_observability_bridge.py

printf '\n== Backend process safety ==\n'
python backend/scripts/check_process_safety.py

printf '\n== Repository process safety ==\n'
python scripts/check_repository_process_safety.py

printf '\n== Backend unsafe deserialization safety ==\n'
python backend/scripts/check_deserialization_safety.py

printf '\n== Repository unsafe deserialization safety ==\n'
python scripts/check_repository_deserialization_safety.py

printf '\n== Backend dynamic import safety ==\n'
python backend/scripts/check_dynamic_import_safety.py

printf '\n== Repository dynamic import safety ==\n'
python scripts/check_repository_dynamic_import_safety.py

printf '\n== Backend tar archive extraction safety ==\n'
python backend/scripts/check_archive_extraction_safety.py

printf '\n== Repository tar archive extraction safety ==\n'
python scripts/check_repository_archive_extraction_safety.py

printf '\n== Security scanner surface preflight ==\n'
python backend/scripts/check_security_scan_surface.py

printf '\n== Defense control-plane contract ==\n'
python scripts/check_defense_control_plane_contract.py

printf '\n== Backend/frontend high-confidence SAST ==\n'
python backend/scripts/check_sast_security.py

printf '\n== Core/tooling Python high-confidence SAST ==\n'
python scripts/check_repository_python_sast.py

printf '\n== JavaScript child_process alias safety ==\n'
python backend/scripts/check_js_process_alias_safety.py

printf '\n== GitHub Actions workflow security ==\n'
python backend/scripts/check_workflow_security.py

printf '\n== GitHub Actions repository allowlist ==\n'
python backend/scripts/check_workflow_action_allowlist.py

printf '\n== GitHub Actions token permissions ==\n'
python backend/scripts/check_workflow_permissions.py

printf '\n== GitHub Actions trigger-fanout audit ==\n'
python backend/scripts/check_workflow_trigger_fanout.py

printf '\n== GitHub Actions concurrency collision audit ==\n'
python backend/scripts/check_workflow_concurrency.py

printf '\n== GitHub Actions workflow_run branch completions ==\n'
python backend/scripts/check_workflow_run_branch_completions.py

printf '\n== Archived dependency-surface quarantine ==\n'
python scripts/check_archived_dependency_surface.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_archived_dependency_surface.py

printf '\n== Repository secret hygiene ==\n'
python backend/scripts/check_secret_hygiene.py

printf '\n== Repository malware / IOC scan ==\n'
python backend/scripts/check_malware_iocs.py

printf '\n== Live-service backend test boundary ==\n'
python backend/scripts/check_live_service_test_boundaries.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  backend/tests/test_live_service_test_boundaries.py

printf '\n== Backend security scanner regressions ==\n'
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  backend/tests/test_exec_guard.py \
  backend/tests/test_auth_security.py \
  backend/tests/test_process_safety_gate.py \
  backend/tests/test_process_safety_destructuring.py \
  backend/tests/test_process_safety_partial.py \
  backend/tests/test_process_safety_namespace_get.py \
  backend/tests/test_process_safety_getattribute.py \
  backend/tests/test_process_safety_helper_aliases.py \
  backend/tests/test_process_safety_scanner_coverage.py \
  backend/tests/test_repository_process_safety.py \
  backend/tests/test_deserialization_safety_gate.py \
  backend/tests/test_repository_deserialization_safety.py \
  backend/tests/test_dynamic_import_safety.py \
  backend/tests/test_dynamic_import_exception_policy.py \
  backend/tests/test_repository_dynamic_import_safety.py \
  backend/tests/test_scanner_nonempty_contract.py \
  backend/tests/test_archive_extraction_safety.py \
  backend/tests/test_unbulk_decompression_security.py \
  backend/tests/test_repository_archive_extraction_safety.py \
  backend/tests/test_security_scan_surface.py \
  backend/tests/test_live_scraper_network_security.py \
  backend/tests/test_free_api_network_security.py \
  backend/tests/test_ai_reader_error_redaction.py \
  backend/tests/test_sast_security_gate.py \
  backend/tests/test_repository_python_sast_scope.py \
  backend/tests/test_js_process_alias_safety.py \
  backend/tests/test_workflow_security_gate.py \
  backend/tests/test_workflow_flow_style_security.py \
  backend/tests/test_workflow_event_context_security.py \
  backend/tests/test_workflow_quoted_key_security.py \
  backend/tests/test_workflow_flow_uses_security.py \
  backend/tests/test_workflow_trigger_security.py \
  backend/tests/test_workflow_trigger_fanout_gate.py \
  backend/tests/test_workflow_security_checkout_credentials.py \
  backend/tests/test_workflow_input_security_gate.py \
  backend/tests/test_workflow_event_shell_security.py \
  backend/tests/test_workflow_action_allowlist.py \
  backend/tests/test_workflow_permissions_gate.py \
  backend/tests/test_workflow_concurrency_gate.py \
  backend/tests/test_workflow_run_branch_completions_contract.py \
  skeleton/testing/test_dependabot_merge_policy.py \
  backend/tests/test_pr_obsolete_run_from_workflow_run.py \
  backend/tests/test_pr_obsolete_run_workflow_run.py \
  backend/tests/test_pr_obsolete_run_sweep.py \
  backend/tests/test_pr_obsolete_run_drain.py \
  backend/tests/test_pr_churn_control.py \
  backend/tests/test_queue_drain_workflow.py \
  backend/tests/test_secret_hygiene_gate.py \
  backend/tests/test_malware_ioc_gate.py \
  backend/tests/test_malware_ioc_io_fail_closed.py \
  backend/tests/test_developer_tooling_security.py \
  backend/tests/test_dependency_security_workflow_contract.py \
  backend/tests/test_incident_response_runbook.py \
  backend/tests/test_api_middleware_adversarial.py \
  backend/tests/test_api_middleware_regression_gaps.py \
  backend/tests/test_proxy_header_bounds.py \
  backend/tests/test_request_identity_logging_security.py \
  backend/tests/test_security_middleware_properties.py \
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
