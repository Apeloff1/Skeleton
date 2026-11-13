"""Adversarial regression for the single audited privileged workflow exception."""
from __future__ import annotations

from pathlib import Path

from scripts import check_workflow_security as policy


ROOT = Path(__file__).resolve().parents[2]
AUDITED = ROOT / ".github" / "workflows" / "pr-merge-hold.yml"


def test_exact_audited_trusted_base_gate_is_admitted() -> None:
    source = AUDITED.read_text(encoding="utf-8")
    assert policy._audited_trusted_target_gate(AUDITED, source)
    assert policy.violations(AUDITED) == []


def test_any_change_to_privileged_gate_revokes_exception(
    tmp_path: Path, monkeypatch
) -> None:
    source = AUDITED.read_text(encoding="utf-8")
    monkeypatch.setattr(policy, "WORKFLOW_DIR", tmp_path)
    target = tmp_path / "pr-merge-hold.yml"
    target.write_text(source.replace("timeout-minutes: 5", "timeout-minutes: 6"), encoding="utf-8")
    assert not policy._audited_trusted_target_gate(target, target.read_text(encoding="utf-8"))
    assert any("pull_request_target is forbidden" in finding for finding in policy.violations(target))


def test_copy_of_privileged_gate_has_no_trigger_authority(
    tmp_path: Path, monkeypatch
) -> None:
    source = AUDITED.read_text(encoding="utf-8")
    monkeypatch.setattr(policy, "WORKFLOW_DIR", tmp_path)
    copied = tmp_path / "shadow-merge-hold.yml"
    copied.write_text(source, encoding="utf-8")
    assert not policy._audited_trusted_target_gate(copied, source)
    assert any("pull_request_target is forbidden" in finding for finding in policy.violations(copied))


def test_noncanonical_directory_cannot_claim_privileged_gate(
    tmp_path: Path, monkeypatch
) -> None:
    source = AUDITED.read_text(encoding="utf-8")
    monkeypatch.setattr(policy, "WORKFLOW_DIR", tmp_path / "expected")
    untrusted = tmp_path / "elsewhere" / "pr-merge-hold.yml"
    untrusted.parent.mkdir()
    untrusted.write_text(source, encoding="utf-8")
    assert not policy._audited_trusted_target_gate(untrusted, source)
    assert any("pull_request_target is forbidden" in finding for finding in policy.violations(untrusted))


def test_foreign_inline_target_trigger_still_denied(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.yml"
    foreign.write_text(
        "name: foreign\non: [pull_request_target]\npermissions:\n  contents: read\n"
        "jobs:\n  noop:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo safe\n",
        encoding="utf-8",
    )
    assert any("pull_request_target is forbidden" in finding for finding in policy.violations(foreign))
