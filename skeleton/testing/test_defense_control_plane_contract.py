from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.check_defense_control_plane_contract import (
    REQUIRED_FILES,
    REQUIRED_TESTS,
    audit,
)


ROOT = Path(__file__).resolve().parents[2]


def _copy_contract_tree(destination: Path) -> None:
    for relative in (*REQUIRED_FILES, *REQUIRED_TESTS):
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _codes(destination: Path) -> set[str]:
    return {finding.code for finding in audit(destination)}


def test_repository_satisfies_defense_control_plane_contract() -> None:
    assert audit(ROOT) == []


def test_missing_required_control_fails_closed(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    (tmp_path / "skeleton/security/defense_plane.py").unlink()

    findings = audit(tmp_path)

    assert "missing" in {item.code for item in findings}
    assert any(
        item.path == "skeleton/security/defense_plane.py"
        for item in findings
    )


def test_symlinked_control_fails_closed(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/scanner_integrity.py"
    path.unlink()
    path.symlink_to(tmp_path / "skeleton/security/defense_plane.py")

    assert "symlink" in _codes(tmp_path)


def test_operator_hold_must_precede_token_access(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/pr_automation/runner.py"
    text = path.read_text(encoding="utf-8")
    token = 'token = os.getenv("GITHUB_TOKEN", "")'
    safety = "safety = load_operator_safety()"
    text = text.replace(safety, "")
    text = text.replace(token, token + "\n    " + safety)
    path.write_text(text, encoding="utf-8")

    assert "token-order" in _codes(tmp_path)


def test_event_admission_must_precede_token_access(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/pr_automation/runner.py"
    text = path.read_text(encoding="utf-8")
    token = 'token = os.getenv("GITHUB_TOKEN", "")'
    admission = "admission = admit_workflow_run(event)"
    text = text.replace(admission, "")
    text = text.replace(token, token + "\n        " + admission)
    path.write_text(text, encoding="utf-8")

    assert "token-order" in _codes(tmp_path)


@pytest.mark.parametrize(
    "marker",
    [
        "SKELETON_AUTOMATION_PAUSED",
        "SKELETON_AUTOMATION_QUARANTINED",
        "SKELETON_AUTOMATION_HOLD_REASON",
    ],
)
def test_workflow_cannot_drop_operator_control(
    tmp_path: Path,
    marker: str,
) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / ".github/workflows/pr-automation-index.yml"
    text = path.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if marker not in line)
    path.write_text(text + "\n", encoding="utf-8")

    assert "operator-env" in _codes(tmp_path)


@pytest.mark.parametrize(
    "marker",
    [
        "WORKFLOW_RUN_ID",
        "WORKFLOW_RUN_ATTEMPT",
        "WORKFLOW_RUN_WORKFLOW_ID",
        "WORKFLOW_RUN_NAME",
        "WORKFLOW_RUN_STATUS",
        "WORKFLOW_RUN_CONCLUSION",
        "WORKFLOW_RUN_EVENT",
        "WORKFLOW_RUN_HEAD_REPOSITORY",
    ],
)
def test_workflow_cannot_drop_authority_metadata(
    tmp_path: Path,
    marker: str,
) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / ".github/workflows/pr-automation-index.yml"
    text = path.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if marker not in line)
    path.write_text(text + "\n", encoding="utf-8")

    assert "workflow-authority-env" in _codes(tmp_path)


def test_cancelled_tombstone_guard_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / ".github/workflows/pr-automation-index.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "github.event.workflow_run.conclusion != 'cancelled'",
        "true",
    )
    path.write_text(text, encoding="utf-8")

    assert "cancelled-tombstone" in _codes(tmp_path)


def test_isolated_python_execution_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / ".github/workflows/pr-automation-index.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("python -I -c", "python -c")
    path.write_text(text, encoding="utf-8")

    assert "isolated-python" in _codes(tmp_path)


def test_persisted_checkout_credentials_are_rejected_by_contract(
    tmp_path: Path,
) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / ".github/workflows/pr-automation-index.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace("persist-credentials: false", "persist-credentials: true")
    path.write_text(text, encoding="utf-8")

    assert "checkout-credentials" in _codes(tmp_path)


def test_event_firewall_mutation_rule_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/pr_automation/event_firewall.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'event.conclusion != "success"',
        'event.conclusion == "success"',
    )
    path.write_text(text, encoding="utf-8")

    assert "event-firewall" in _codes(tmp_path)


def test_automation_circuit_breaker_contract_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/automation/control_plane.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("class CircuitBreaker", "class RemovedCircuitBreaker")
    path.write_text(text, encoding="utf-8")

    assert "automation-control" in _codes(tmp_path)


def test_lockdown_observe_only_contract_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/defense_plane.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "only observation is permitted in lockdown mode",
        "lockdown allows reads",
    )
    path.write_text(text, encoding="utf-8")

    assert "defense-plane" in _codes(tmp_path)


def test_incident_recovery_authority_contract_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/incident_containment.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("class RecoveryAuthority", "class RemovedRecoveryAuthority")
    path.write_text(text, encoding="utf-8")

    assert "incident-containment" in _codes(tmp_path)


def test_scanner_self_failure_contract_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/scanner_integrity.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "security scanner self-failure detected",
        "scanner warning",
    )
    path.write_text(text, encoding="utf-8")

    assert "scanner-integrity" in _codes(tmp_path)


def test_legacy_scanner_never_run_score_contract_is_required(
    tmp_path: Path,
) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/vuln_scanner.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("return 0.0", "return 100.0", 1)
    path.write_text(text, encoding="utf-8")

    assert "legacy-scanner" in _codes(tmp_path)


def test_outbound_peer_binding_contract_is_required(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "skeleton/security/outbound_url.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "def validate_connected_peer(",
        "def removed_validate_connected_peer(",
    )
    path.write_text(text, encoding="utf-8")

    assert "outbound-boundary" in _codes(tmp_path)


def test_all_new_adversarial_tests_must_remain_in_quality_gate(
    tmp_path: Path,
) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "scripts/quality-gates.sh"
    text = path.read_text(encoding="utf-8")
    removed = REQUIRED_TESTS[0]
    text = text.replace(removed, "removed-security-test.py")
    path.write_text(text, encoding="utf-8")

    assert "quality-gate-tests" in _codes(tmp_path)


def test_contract_checker_must_remain_in_quality_gate(tmp_path: Path) -> None:
    _copy_contract_tree(tmp_path)
    path = tmp_path / "scripts/quality-gates.sh"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "python scripts/check_defense_control_plane_contract.py",
        "echo removed-defense-contract",
    )
    path.write_text(text, encoding="utf-8")

    assert "quality-gate-contract" in _codes(tmp_path)
