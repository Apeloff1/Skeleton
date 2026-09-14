from __future__ import annotations

import hashlib
import json

import pytest

from core.deployment_receipts import DeploymentReceiptIntegrityError, DeploymentReceiptLedger


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


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


def _rehash(row: dict) -> dict:
    candidate = dict(row)
    payload = {key: value for key, value in candidate.items() if key != "sha256"}
    candidate["sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return candidate


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


def test_rehashed_receipt_schema_extension_is_rejected(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger)
    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["operator_override"] = True
    row = _rehash(row)
    ledger.path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(DeploymentReceiptIntegrityError, match="schema mismatch"):
        DeploymentReceiptLedger(tmp_path)


def test_rehashed_boolean_sequence_is_rejected(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    _record(ledger)
    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["sequence"] = True
    row = _rehash(row)
    ledger.path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(DeploymentReceiptIntegrityError, match="sequence malformed"):
        DeploymentReceiptLedger(tmp_path)


def test_non_string_identity_input_is_not_silently_coerced(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    with pytest.raises(ValueError, match="authorization_id must be a string"):
        ledger.record(
            authorization_id=123,
            plan_sha256="1" * 64,
            release_id="release-1",
            release_sha256="2" * 64,
            target="runtime",
            environment="production",
            artifact="sha256:artifact",
            pre_system_root_sha256="a" * 64,
            post_system_root_sha256="b" * 64,
        )


def test_uppercase_digest_is_rejected_instead_of_normalized(tmp_path):
    ledger = DeploymentReceiptLedger(tmp_path)
    with pytest.raises(ValueError, match="plan must be sha256"):
        ledger.record(
            authorization_id="auth-1",
            plan_sha256="A" * 64,
            release_id="release-1",
            release_sha256="2" * 64,
            target="runtime",
            environment="production",
            artifact="sha256:artifact",
            pre_system_root_sha256="a" * 64,
            post_system_root_sha256="b" * 64,
        )
