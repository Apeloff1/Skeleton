"""Focused fail-closed regressions for durable session recovery."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.durable_recovery import DurableSessionRecoveryVerifier


class _Chain:
    def snapshot(self):
        return ()

    def verify(self) -> bool:
        return True

    def root_hash(self) -> str:
        return "0" * 64


def _verifier(**overrides):
    kwargs = {
        "finalizations": object(),
        "recovery_checkpoints": object(),
        "session_evidence": object(),
        "journal": _Chain(),
        "receipt_chain": _Chain(),
    }
    kwargs.update(overrides)
    return DurableSessionRecoveryVerifier(**kwargs)


def test_minimal_recovery_verifier_is_fail_closed_but_constructible():
    verifier = _verifier()
    assert verifier.journal_archive is None
    assert verifier.receipt_archive is None
    assert verifier.proof_windows is None
    assert verifier.require_session_commit is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"journal_archive": object()}, "journal_archive and journal_chain_id"),
        ({"journal_chain_id": "journal"}, "journal_archive and journal_chain_id"),
        ({"receipt_archive": object()}, "receipt_archive and receipt_chain_id"),
        ({"receipt_chain_id": "receipt"}, "receipt_archive and receipt_chain_id"),
        (
            {"journal_proof_chain_id": "journal"},
            "proof chain ids require proof_windows operator",
        ),
        (
            {"receipt_proof_chain_id": "receipt"},
            "proof chain ids require proof_windows operator",
        ),
        (
            {"require_session_commit": True},
            "required session commit store is not configured",
        ),
    ],
)
def test_recovery_configuration_rejects_partial_authority(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _verifier(**kwargs)


@pytest.mark.parametrize("value", [0, 1, "yes", None])
def test_require_session_commit_must_be_boolean(value):
    with pytest.raises(ValueError, match="require_session_commit must be bool"):
        _verifier(require_session_commit=value)


def test_journal_and_receipt_chains_must_expose_integrity_contract():
    with pytest.raises(TypeError, match="journal does not implement snapshot"):
        DurableSessionRecoveryVerifier(
            finalizations=object(),
            recovery_checkpoints=object(),
            session_evidence=object(),
            journal=object(),
            receipt_chain=_Chain(),
        )

    with pytest.raises(TypeError, match="receipt_chain does not implement snapshot"):
        DurableSessionRecoveryVerifier(
            finalizations=object(),
            recovery_checkpoints=object(),
            session_evidence=object(),
            journal=_Chain(),
            receipt_chain=object(),
        )
