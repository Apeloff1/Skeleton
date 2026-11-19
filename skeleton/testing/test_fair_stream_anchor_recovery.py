"""Forward-only recovery qualification with a simulated independent anchor."""
from dataclasses import replace
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from skeleton.ai.model_runtime.fair_stream_anchor_recovery import (
    AnchorRecoveryDenied, inspect_forward_candidate, issue_forward_approval,
    recover_forward_anchor,
)
from skeleton.ai.model_runtime.fair_stream_session import CustodyQuarantined, DurableFairStreamSession
from skeleton.testing.test_fair_stream_session import (
    SimulatedIndependentWatermark, budget, request, store,
)


def failed_transition(*, pending=False):
    anchor = SimulatedIndependentWatermark()
    db = store()
    old = DurableFairStreamSession.bootstrap(db, anchor)
    if pending:
        old.submit(request())
    anchor.fail_advance = True
    with pytest.raises(CustodyQuarantined):
        if pending:
            old.plan(budget())
        else:
            old.submit(request())
    anchor.fail_advance = False
    return db, anchor, old


def approved(db, anchor):
    signing = Ed25519PrivateKey.generate()
    candidate = inspect_forward_candidate(db, anchor)
    return issue_forward_approval(candidate, nonce="a" * 32, signing_key=signing), signing.public_key()


@pytest.mark.parametrize("pending", [False, True])
def test_operator_forward_recovery_keeps_exact_state_and_no_lease_reissue(pending):
    db, anchor, old = failed_transition(pending=pending)
    approval, key = approved(db, anchor)
    prior = db._connection.execute(
        "SELECT payload FROM local_fair_stream_custody"
    ).fetchone()
    recovered = recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert old.quarantined
    assert recovered.verify()["digest"] == approval.candidate.next_digest
    assert len(recovered.pending_ids()) == int(pending)
    assert db._connection.execute(
        "SELECT payload FROM local_fair_stream_custody"
    ).fetchone() == prior
    with pytest.raises(AnchorRecoveryDenied, match="one-generation"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    if pending:
        with pytest.raises(CustodyQuarantined):
            recovered.plan(budget())


def test_wrong_signer_or_tampered_approval_never_advances_anchor():
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    prior = anchor.read()
    for grant, verifier in (
        (approval, Ed25519PrivateKey.generate().public_key()),
        (replace(approval, nonce="b" * 32), key),
    ):
        with pytest.raises(AnchorRecoveryDenied, match="signature"):
            recover_forward_anchor(db, anchor, approval=grant, operator_public_key=verifier)
        assert anchor.read() == prior


def test_wrong_lineage_and_corrupt_payload_do_not_become_authority():
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    anchor.state = (anchor.state[0], "f" * 64)
    with pytest.raises(AnchorRecoveryDenied, match="descend"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    anchor.state = (approval.candidate.prior_generation, approval.candidate.prior_digest)
    db._connection.execute("UPDATE local_fair_stream_custody SET payload=?", (b"{}",))
    db._connection.commit()
    with pytest.raises(ValueError):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert anchor.read() == (approval.candidate.prior_generation, approval.candidate.prior_digest)


def test_cas_failure_does_not_return_session_or_leave_transaction():
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    anchor.fail_advance = True
    with pytest.raises(OSError):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert anchor.read() == (approval.candidate.prior_generation, approval.candidate.prior_digest)


def test_missing_anchor_or_rolled_back_database_cannot_be_repaired():
    db = store(sqlite3.connect(":memory:"))
    anchor = SimulatedIndependentWatermark()
    DurableFairStreamSession.bootstrap(db, anchor)
    anchor.state = (1, "f" * 64)
    with pytest.raises(AnchorRecoveryDenied, match="one-generation"):
        inspect_forward_candidate(db, anchor)
    anchor.state = None
    with pytest.raises(ValueError):
        inspect_forward_candidate(db, anchor)
    assert not db._connection.in_transaction


def test_interrupted_anchor_advancement_quarantines_old_session():
    anchor = SimulatedIndependentWatermark()
    db = store()
    old = DurableFairStreamSession.bootstrap(db, anchor)
    def interrupted(**kwargs):
        raise KeyboardInterrupt
    anchor.advance = interrupted
    with pytest.raises(KeyboardInterrupt):
        old.submit(request())
    assert old.quarantined
