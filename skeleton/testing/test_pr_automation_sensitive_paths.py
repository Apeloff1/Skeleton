from __future__ import annotations

from skeleton.pr_automation.core import CIState, Decision, PRSnapshot, Policy, evaluate
from skeleton.pr_automation.runner import _scan_sensitive_paths


def _snapshot(*, sensitive_paths=()):
    return PRSnapshot(
        repository="Apeloff1/Skeleton",
        number=42,
        head_sha="a" * 40,
        base_sha="b" * 40,
        base_ref="main",
        head_ref="feature/example",
        mergeable=True,
        mergeable_state="clean",
        ci_state=CIState.PASSING,
        approvals=1,
        changes_requested=0,
        unresolved_threads=0,
        changed_files=1,
        additions=10,
        deletions=1,
        sensitive_paths=sensitive_paths,
    )


def test_sensitive_trust_surface_is_never_automatic_merge_material():
    result = evaluate(
        _snapshot(sensitive_paths=(".github/workflows/ci.yml",)),
        Policy(required_approvals=1, merge_when_ready=True),
    )
    assert result.decision is Decision.HOLD
    assert "trust surface" in result.reasons[0]


def test_incomplete_changed_file_scan_fails_closed():
    result = evaluate(
        _snapshot(sensitive_paths=None),
        Policy(required_approvals=1, merge_when_ready=True),
    )
    assert result.decision is Decision.HOLD
    assert "incomplete" in result.reasons[0]


def test_sensitive_path_classifier_covers_automation_and_gate_controls():
    files = [
        {"filename": ".github/workflows/ci.yml"},
        {"filename": ".github/ci/flaky-quarantine.json"},
        {"filename": "skeleton/pr_automation/runner.py"},
        {"filename": "scripts/check_merge_readiness_contract.py"},
        {"filename": "scripts/quality-gates.sh"},
        {"filename": "tests/run_unit.py"},
        {"filename": "docs/readme.md"},
        {"filename": "frontend/src/app.tsx"},
    ]
    assert _scan_sensitive_paths(files) == (
        ".github/ci/flaky-quarantine.json",
        ".github/workflows/ci.yml",
        "scripts/check_merge_readiness_contract.py",
        "scripts/quality-gates.sh",
        "skeleton/pr_automation/runner.py",
        "tests/run_unit.py",
    )


def test_normal_application_changes_remain_eligible():
    result = evaluate(
        _snapshot(sensitive_paths=()),
        Policy(required_approvals=1, merge_when_ready=True),
    )
    assert result.decision is Decision.MERGE
