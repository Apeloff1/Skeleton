#!/usr/bin/env python3
"""Fail when canonical local and backend CI quality gates drift apart."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUFF_DEV_REQUIREMENT = "ruff>=0.9,<0.17"

# These are intentionally behavior-oriented markers rather than exact whole
# command lines so local execution may use ``python -m`` while CI can invoke a
# console script from its pinned environment.
SHARED_BACKEND_MARKERS: tuple[tuple[str, str], ...] = (
    ("Ruff lint", "ruff check . --output-format=github"),
    ("architecture boundary scanner", "check_architecture_boundaries.py"),
    ("architecture boundary regression", "test_architecture_boundaries.py"),
    ("provider runtime boundary scanner", "check_provider_runtime_boundary.py"),
    ("provider runtime boundary regression", "test_provider_runtime_boundary.py"),
    ("process invocation safety", "check_process_safety.py"),
    ("unsafe deserialization safety", "check_deserialization_safety.py"),
    ("dynamic import safety", "check_dynamic_import_safety.py"),
    ("dynamic import regression", "test_dynamic_import_safety.py"),
    ("tar archive extraction safety", "check_archive_extraction_safety.py"),
    ("tar archive extraction regression", "test_archive_extraction_safety.py"),
    ("security scanner surface preflight", "check_security_scan_surface.py"),
    ("security scanner surface regression", "test_security_scan_surface.py"),
    ("live scraper network regression", "test_live_scraper_network_security.py"),
    ("high-confidence SAST", "check_sast_security.py"),
    ("high-confidence SAST regression", "test_sast_security_gate.py"),
    ("repository Python SAST", "check_repository_python_sast.py"),
    ("repository Python SAST regression", "test_repository_python_sast_scope.py"),
    ("JavaScript process alias safety", "check_js_process_alias_safety.py"),
    ("workflow security", "check_workflow_security.py"),
    ("workflow security regression", "test_workflow_security_gate.py"),
    ("workflow action allowlist", "check_workflow_action_allowlist.py"),
    ("workflow action allowlist regression", "test_workflow_action_allowlist.py"),
    ("workflow token permissions", "check_workflow_permissions.py"),
    ("workflow token permissions regression", "test_workflow_permissions_gate.py"),
    ("workflow checkout credential regression", "test_workflow_security_checkout_credentials.py"),
    ("workflow input security regression", "test_workflow_input_security_gate.py"),
    ("workflow event shell regression", "test_workflow_event_shell_security.py"),
    ("workflow flow-style regression", "test_workflow_flow_style_security.py"),
    ("workflow event-context regression", "test_workflow_event_context_security.py"),
    ("workflow quoted-key regression", "test_workflow_quoted_key_security.py"),
    ("workflow flow-uses regression", "test_workflow_flow_uses_security.py"),
    ("workflow trigger regression", "test_workflow_trigger_security.py"),
    ("workflow trigger-fanout", "check_workflow_trigger_fanout.py"),
    ("workflow trigger-fanout regression", "test_workflow_trigger_fanout_gate.py"),
    ("workflow concurrency", "check_workflow_concurrency.py"),
    ("workflow concurrency regression", "test_workflow_concurrency_gate.py"),
    ("workflow_run branch completions", "check_workflow_run_branch_completions.py"),
    ("workflow_run branch completions regression", "test_workflow_run_branch_completions_contract.py"),
    ("authentication security regression", "test_auth_security.py"),
    ("developer tooling security regression", "test_developer_tooling_security.py"),
    ("API middleware adversarial regression", "test_api_middleware_adversarial.py"),
    ("API middleware regression-gap coverage", "test_api_middleware_regression_gaps.py"),
    ("proxy header bounds regression", "test_proxy_header_bounds.py"),
    ("request identity logging security regression", "test_request_identity_logging_security.py"),
    ("security middleware property regression", "test_security_middleware_properties.py"),
    ("secret hygiene", "check_secret_hygiene.py"),
    ("malware/IOC policy", "check_malware_iocs.py"),
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def active_text(text: str) -> str:
    """Ignore comment-only lines so documentation cannot satisfy a gate marker."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def main() -> int:
    local = active_text(read("scripts/quality-gates.sh"))
    ci = active_text(read(".github/workflows/backend-quality.yml"))
    precommit = active_text(read(".pre-commit-config.yaml"))
    requirements_dev = {
        line.strip()
        for line in read("requirements-dev.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    root_project = tomllib.loads(read("pyproject.toml"))
    root_dev = root_project.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    failures: list[str] = []

    for label, marker in SHARED_BACKEND_MARKERS:
        if marker not in local:
            failures.append(f"local quality gate missing {label}: {marker}")
        if marker not in ci:
            failures.append(f"Backend Quality CI missing {label}: {marker}")

    if "python -m compileall -q backend" not in local:
        failures.append("local quality gate must compile the full backend tree")
    if "python -m compileall -q ." not in ci:
        failures.append("Backend Quality CI must compile the full backend tree")

    if "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" not in local or "--noconftest" not in local:
        failures.append("local focused regressions must run with pytest plugin/conftest isolation")
    if 'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' not in ci or "--noconftest" not in ci:
        failures.append("Backend Quality focused regressions must run with pytest plugin/conftest isolation")

    if "yarn --cwd frontend lint:ci" not in local or "yarn --cwd frontend typecheck" not in local:
        failures.append("local canonical quality gate must keep frontend lint and typecheck coverage")

    parity_command = "python scripts/check_quality_gate_parity.py"
    if parity_command not in local:
        failures.append("local canonical quality gate must execute the parity guard")
    if parity_command not in ci:
        failures.append("Backend Quality CI must execute the parity guard")
    if "canonical-quality-parity" not in precommit or parity_command not in precommit:
        failures.append("pre-commit must execute the canonical quality parity guard")

    if ci.count('"scripts/check_quality_gate_parity.py"') < 2:
        failures.append("Backend Quality must trigger on parity-guard changes for push and pull_request")
    if ci.count('"scripts/quality-gates.sh"') < 2:
        failures.append("Backend Quality must trigger on local canonical-gate changes for push and pull_request")
    if ci.count('"scripts/check_repository_python_sast.py"') < 2:
        failures.append(
            "Backend Quality must trigger on repository Python SAST changes for push and pull_request"
        )

    if RUFF_DEV_REQUIREMENT not in requirements_dev:
        failures.append(f"requirements-dev.txt must include {RUFF_DEV_REQUIREMENT}")
    if RUFF_DEV_REQUIREMENT not in root_dev:
        failures.append(f"root dev optional dependencies must include {RUFF_DEV_REQUIREMENT}")

    if failures:
        print("Canonical quality gate parity violations:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(
        "Canonical quality gate parity passed: local, CI, pre-commit, triggers, and dev tooling "
        "retain the shared lint, architecture, provider-boundary, security, syntax, and isolated-"
        "regression contract."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
