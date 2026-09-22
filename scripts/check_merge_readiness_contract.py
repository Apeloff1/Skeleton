#!/usr/bin/env python3
"""Fail closed if the canonical merge-readiness workflow drifts from policy."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/merge-readiness.yml"
PYTHON_VERSION = "3.11.16"
NODE_VERSION = "24.20.0"
RUFF_VERSION = "0.9.10"
GITLEAKS_PIN = "gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e"
REQUIRED_NEEDS = (
    "quarantine_policy",
    "unit",
    "integration_smoke",
    "quality_security",
    "pr_automation",
)
PR_AUTOMATION_TESTS = (
    "skeleton/testing/test_pr_automation.py",
    "skeleton/testing/test_pr_automation_ruleset.py",
    "skeleton/testing/test_pr_automation_sensitive_paths.py",
    "skeleton/testing/test_pr_automation_workflow.py",
    "skeleton/testing/test_pr_automation_branch_completions.py",
    "skeleton/testing/test_runner_v2_contracts.py",
    "skeleton/testing/test_runner_v2_evidence.py",
    "skeleton/testing/test_runner_v2_runtime.py",
    "skeleton/testing/test_runner_v2_transaction_report.py",
    "skeleton/testing/test_runner_v2_engine.py",
)
CONCURRENCY_GROUP = "group: merge-readiness-${{ github.event.pull_request.number || github.sha }}"
CANCEL_POLICY = "cancel-in-progress: ${{ github.event_name == 'pull_request' }}"
READINESS_GUARD = (
    "if: ${{ always() && (github.event_name != 'pull_request' || "
    "(!github.event.pull_request.draft && github.event.action != 'converted_to_draft' "
    "&& github.event.action != 'closed')) }}"
)
JOB_HEADER_RE = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*$", re.MULTILINE)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def job_block(text: str, job_name: str) -> str:
    """Return one top-level workflow job block without leaking into later jobs."""
    target = re.search(rf"^  {re.escape(job_name)}:\s*$", text, re.MULTILINE)
    if target is None:
        return ""

    next_job = JOB_HEADER_RE.search(text, target.end())
    end = next_job.start() if next_job is not None else len(text)
    return text[target.start() : end]


def main() -> int:
    failures: list[str] = []
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"merge-readiness contract: cannot read workflow: {exc}")

    require("workflow_dispatch:" in text, "merge-readiness must support explicit current-head verification", failures)
    require("concurrency:" in text, "merge-readiness concurrency policy missing", failures)
    require(
        CONCURRENCY_GROUP in text,
        "merge-readiness concurrency must deduplicate PRs while preserving each main head SHA",
        failures,
    )
    require(
        CANCEL_POLICY in text,
        "only superseded pull-request merge-readiness runs may be cancelled",
        failures,
    )
    require(
        "cancel-in-progress: true" not in text,
        "unconditional merge-readiness cancellation can erase canonical main verification evidence",
        failures,
    )
    require(
        "github.event.pull_request.number || github.ref" not in text,
        "branch-ref merge-readiness grouping can starve main verification during rapid merges",
        failures,
    )
    require(
        re.search(r'^\s*PYTHON_VERSION:\s*"3\.11\.16"\s*$', text, re.MULTILINE) is not None,
        f"Python must be pinned to {PYTHON_VERSION}",
        failures,
    )
    require(
        re.search(r'^\s*NODE_VERSION:\s*"24\.20\.0"\s*$', text, re.MULTILINE) is not None,
        f"Node must be pinned to {NODE_VERSION}",
        failures,
    )
    require(
        text.count('python-version: "${{ env.PYTHON_VERSION }}"') == 5,
        "all five Python setup sites must consume PYTHON_VERSION",
        failures,
    )
    require(
        'node-version: "${{ env.NODE_VERSION }}"' in text,
        "Node setup must consume NODE_VERSION",
        failures,
    )
    require(f'"ruff=={RUFF_VERSION}"' in text, f"Ruff must be pinned to {RUFF_VERSION}", failures)
    require("ruff==0.9.*" not in text, "wildcard Ruff execution is forbidden", failures)
    require(
        "--frozen-lockfile --non-interactive" in text,
        "frontend install must be frozen and non-interactive",
        failures,
    )
    require("python scripts/check_flaky_quarantine.py" in text, "quarantine policy checker must run", failures)
    require("bash scripts/quality-gates.sh" in text, "canonical quality/security gates must run", failures)
    require(GITLEAKS_PIN in text, "full-history Gitleaks action pin drifted", failures)
    require("continue-on-error: true" not in text, "required merge gates must not hide failures", failures)
    require(
        'ports:\n          - "27017:27017"' in text,
        "Mongo service port must use explicit quoted list syntax",
        failures,
    )

    quality_security = job_block(text, "quality_security")
    require(bool(quality_security), "quality/security validation job missing", failures)
    require(
        '"pytest-asyncio>=0.24,<2"' in quality_security,
        "quality/security job must install the explicit asyncio test plugin",
        failures,
    )
    try:
        quality_gates = (ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"merge-readiness contract: cannot read quality gates: {exc}")
    require(
        "-p pytest_asyncio.plugin" in quality_gates,
        "quality gates must explicitly load pytest-asyncio while plugin autoload is disabled",
        failures,
    )

    pr_automation = job_block(text, "pr_automation")
    require(bool(pr_automation), "PR automation validation job missing", failures)
    require("name: PR Automation Tests" in pr_automation, "stable PR Automation Tests job name missing", failures)
    normalized_pr_automation = " ".join(pr_automation.split())
    require(
        "python -m compileall -q skeleton/pr_automation" in normalized_pr_automation,
        "PR automation package compilation gate missing",
        failures,
    )
    require(
        "python scripts/check_automerge_contract.py" in pr_automation,
        "auto-merge privileged contract checker missing",
        failures,
    )
    require(
        "python scripts/check_runner_v2_contract.py" in pr_automation,
        "runner-v2 privileged contract checker missing",
        failures,
    )
    require(
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in pr_automation,
        "PR automation tests must disable ambient pytest plugins",
        failures,
    )
    require("--noconftest" in pr_automation, "PR automation tests must avoid unrelated conftest state", failures)
    for test_path in PR_AUTOMATION_TESTS:
        require(test_path in pr_automation, f"PR automation gate missing {test_path}", failures)
    require(
        "name: Run supervisor workflow contract in isolated import namespace" in pr_automation,
        "supervisor workflow contract must run in an isolated pytest invocation",
        failures,
    )
    require(
        "--import-mode=importlib" in pr_automation
        and "backend/tests/test_supervisor_workflow_contract.py" in pr_automation,
        "backend supervisor workflow contract must use collision-safe import isolation",
        failures,
    )

    readiness = job_block(text, "readiness")
    require(bool(readiness), "readiness job missing", failures)
    require("name: Merge Readiness" in readiness, "stable Merge Readiness job name missing", failures)
    require(
        READINESS_GUARD in readiness,
        "Merge Readiness must aggregate active validation runs while preserving draft/close cancellation barriers",
        failures,
    )
    require('result != "success"' in readiness, "Merge Readiness must fail on every non-success result", failures)
    for job in REQUIRED_NEEDS:
        require(
            re.search(rf"^\s+-\s+{re.escape(job)}\s*$", readiness, re.MULTILINE) is not None,
            f"Merge Readiness missing required dependency {job}",
            failures,
        )
        require(
            f"needs.{job}.result" in readiness,
            f"Merge Readiness missing explicit result binding for {job}",
            failures,
        )

    require((ROOT / ".github/ci/flaky-quarantine.json").is_file(), "flaky quarantine registry missing", failures)
    require((ROOT / "scripts/check_flaky_quarantine.py").is_file(), "flaky quarantine checker missing", failures)

    if failures:
        print("Merge-readiness contract violations:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        "Merge-readiness contract passed: stable aggregate, exact toolchain, PR-safe supersession, "
        "non-cancelling main verification, quarantine/security/secret gates, focused PR automation "
        "contracts, and explicit fail-closed result aggregation are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
