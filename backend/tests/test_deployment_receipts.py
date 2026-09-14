from __future__ import annotations

import json

import pytest

from core.deployment_receipts import DeploymentReceiptIntegrityError, DeploymentReceiptLedger


def _record(ledger: DeploymentReceiptLedger, *, authorization_id: str = "auth-1", release_id: str = "release-1",
            pre: str = "a", post: str = "b", executed_at: str = "2026-09-14T12:00:00+00:00"):
    return ledger.record(
        authorization_id=authorization_id,
        plan_sha256="1" * 64,
        release_id=release_id,
        release_sha256="2" * 64,
        target="runtime",
        environment="production",
        artifact="sha256:artifact",
        pre_system_root_sha256=pre * 64,
        post_system_root_sha256=post * 64,
        executed_at=executed_at,
    )


def test_receipts_persist_hash_chain_and_reload(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    first = _record(ledger, authorization_id="auth-1", release_id="release-1", pre="a", post="b")
    second = _record(ledger, authorization_id="auth-2", release_id="release-2", pre="b", post="c",
                     executed_at="2026-09-14T12:00:01+00:00")

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_sha256 == first.sha256
    assert DeploymentReceiptLedger(tmp_path).snapshot() == (first, second)
    assert ledger.status()["verified"] is True


def test_identical_replay_is_idempotent(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    first = _record(ledger)
    replay = _record(ledger, executed_at="2026-09-14T12:05:00+00:00")

    assert replay == first
    assert len(ledger.snapshot()) == 1


def test_same_authorization_cannot_attest_conflicting_transition(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger)

    with pytest.raises(DeploymentReceiptIntegrityError, match="conflicting"):
        _record(ledger, post="c")
    assert len(ledger.snapshot()) == 1


def test_release_cannot_be_attested_by_second_authorization(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger, authorization_id="auth-1", release_id="release-1")

    with pytest.raises(DeploymentReceiptIntegrityError, match="another authorization"):
        _record(ledger, authorization_id="auth-2", release_id="release-1", pre="b", post="c")


def test_receipt_requires_actual_system_root_transition(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)

    with pytest.raises(ValueError, match="system-root transition"):
        _record(ledger, pre="a", post="a")
    assert ledger.snapshot() == ()


def test_tampered_persisted_receipt_fails_closed(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger)
    path = tmp_path / "deployment-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["artifact"] = "sha256:tampered"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(DeploymentReceiptIntegrityError, match="hash mismatch"):
        DeploymentReceiptLedger(tmp_path)


def test_persisted_noop_transition_is_rejected_even_with_existing_hash(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger)
    path = tmp_path / "deployment-receipts.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["post_system_root_sha256"] = row["pre_system_root_sha256"]
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(DeploymentReceiptIntegrityError, match="system-root transition"):
        DeploymentReceiptLedger(tmp_path)


def test_naive_timestamp_is_rejected(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        _record(ledger, executed_at="2026-09-14T12:00:00")
