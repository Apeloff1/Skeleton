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


def test_anchor_acknowledgement_without_persisted_advance_is_not_authority():
    db = store()
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    original = anchor.read()
    anchor.advance = lambda **kwargs: None
    with pytest.raises(CustodyQuarantined, match="reconciliation"):
        session.submit(request())
    assert session.quarantined
    assert anchor.read() == original
    assert inspect_forward_candidate(db, anchor).next_generation == original[0] + 1


def test_forward_approval_cannot_recover_changed_successor():
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    prior = anchor.read()
    db._connection.execute("UPDATE local_fair_stream_custody SET digest=?", ("f" * 64,))
    db._connection.commit()
    with pytest.raises(ValueError):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert anchor.read() == prior
    assert not db._connection.in_transaction


def test_native_policy_remains_authenticated_during_forward_recovery():
    from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore
    from skeleton.ai.model_runtime.fair_stream_queue import StreamRequest
    from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase
    from skeleton.testing.test_fair_stream_session import C, E, SESSION
    db = DurableFairStreamStore(sqlite3.connect(":memory:"), custody_key=C,
                               execution_key=E, session_id=SESSION, whole_request=True)
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    anchor.fail_advance = True
    with pytest.raises(CustodyQuarantined):
        session.submit(StreamRequest("native", "tenant", InferencePhase.PREFILL, 4, 4,
                                     authorization_digest="f" * 64))
    anchor.fail_advance = False
    approval, key = approved(db, anchor)
    recovered = recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert recovered.whole_request
    assert recovered.verify()["checkpoint"]["requests"][0]["authorization_digest"] == "f" * 64
    with pytest.raises(ValueError, match="execution policy"):
        recovered.plan(budget(), whole_request=False)

def test_candidate_rejects_anchor_change_during_authenticated_restore(monkeypatch):
    db, anchor, _ = failed_transition()
    original = db._restore

    def moved(*args, **kwargs):
        owner = original(*args, **kwargs)
        anchor.state = (123, "e" * 64)
        return owner

    monkeypatch.setattr(db, "_restore", moved)
    with pytest.raises(AnchorRecoveryDenied, match="anchor changed"):
        inspect_forward_candidate(db, anchor)
    assert not db._connection.in_transaction


def test_forward_recovery_refuses_anchor_callback_that_releases_writer_reservation(monkeypatch):
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    original = anchor.advance

    def releases(**kwargs):
        original(**kwargs)
        db._connection.commit()

    monkeypatch.setattr(anchor, "advance", releases)
    with pytest.raises(AnchorRecoveryDenied, match="writer reservation"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert anchor.read() == (approval.candidate.next_generation, approval.candidate.next_digest)


def test_forward_recovery_refuses_changed_successor_after_anchor_commit(monkeypatch):
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    original = anchor.advance

    def changed(**kwargs):
        original(**kwargs)
        db._connection.execute("UPDATE local_fair_stream_custody SET payload=?", (b"{}",))

    monkeypatch.setattr(anchor, "advance", changed)
    with pytest.raises(AnchorRecoveryDenied, match="successor changed"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert DurableFairStreamSession(db, anchor).verify()["digest"] == approval.candidate.next_digest


def test_composed_forward_authority_rejects_self_signed_candidate():
    from cryptography.hazmat.primitives import serialization
    from skeleton.ai.model_runtime.fair_stream_anchor_recovery import ForwardAnchorRecoveryAuthority

    db, anchor, _ = failed_transition()
    operator = Ed25519PrivateKey.generate()
    authority = ForwardAnchorRecoveryAuthority(
        store=db, watermark=anchor, operator_public_key=operator.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        ),
    )
    candidate = authority.inspect()
    prior = anchor.read()
    attacker = issue_forward_approval(candidate, nonce="a" * 32,
                                      signing_key=Ed25519PrivateKey.generate())
    with pytest.raises(AnchorRecoveryDenied, match="signature"):
        authority.recover(attacker)
    assert anchor.read() == prior
    grant = issue_forward_approval(candidate, nonce="b" * 32, signing_key=operator)
    assert authority.recover(grant).verify()["digest"] == candidate.next_digest

@pytest.mark.parametrize("release_at", [1, 2])
def test_candidate_rejects_reservation_release_from_anchor_read(monkeypatch, release_at):
    db, anchor, _ = failed_transition()
    original = anchor.read
    calls = 0

    def read():
        nonlocal calls
        calls += 1
        if calls == release_at:
            db._connection.commit()
        return original()

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises(AnchorRecoveryDenied, match="writer reservation"):
        inspect_forward_candidate(db, anchor)
    assert not db._connection.in_transaction


def test_final_anchor_read_cannot_release_writer_reservation(monkeypatch):
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    original = anchor.read
    confirmed = 0

    def read():
        nonlocal confirmed
        current = original()
        if current[0] == approval.candidate.next_generation:
            confirmed += 1
            if confirmed == 2:
                db._connection.commit()
        return current

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises(AnchorRecoveryDenied, match="writer reservation"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert original() == (approval.candidate.next_generation, approval.candidate.next_digest)


def test_final_anchor_read_cannot_mutate_approved_payload(monkeypatch):
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    original = anchor.read
    confirmed = 0

    def read():
        nonlocal confirmed
        current = original()
        if current[0] == approval.candidate.next_generation:
            confirmed += 1
            if confirmed == 2:
                db._connection.execute("UPDATE local_fair_stream_custody SET payload=?", (b"{}",))
        return current

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises(AnchorRecoveryDenied, match="final readback"):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert DurableFairStreamSession(db, anchor).verify()["digest"] == approval.candidate.next_digest


@pytest.mark.parametrize("mutation", ["row", "ddl"])
def test_initial_anchor_read_cannot_mutate_candidate(monkeypatch, mutation):
    db, anchor, _ = failed_transition()
    original = anchor.read
    calls = 0
    before = db._connection.execute(
        "SELECT payload FROM local_fair_stream_custody"
    ).fetchone()

    def read():
        nonlocal calls
        calls += 1
        if calls == 1:
            if mutation == "row":
                db._connection.execute(
                    "UPDATE local_fair_stream_custody SET payload=payload"
                )
            else:
                db._connection.execute("CREATE TABLE unexpected_anchor_state (id INTEGER)")
        return original()

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises((AnchorRecoveryDenied, ValueError)):
        inspect_forward_candidate(db, anchor)
    assert not db._connection.in_transaction
    assert db._connection.execute(
        "SELECT payload FROM local_fair_stream_custody"
    ).fetchone() == before
    assert db._connection.execute(
        "SELECT name FROM sqlite_master WHERE name='unexpected_anchor_state'"
    ).fetchone() is None


def test_final_anchor_read_cannot_change_unrelated_schema(monkeypatch):
    db, anchor, _ = failed_transition()
    approval, key = approved(db, anchor)
    original = anchor.read
    confirmed = 0

    def read():
        nonlocal confirmed
        current = original()
        if current[0] == approval.candidate.next_generation:
            confirmed += 1
            if confirmed == 2:
                db._connection.execute("CREATE TABLE unexpected_anchor_state (id INTEGER)")
        return current

    monkeypatch.setattr(anchor, "read", read)
    with pytest.raises((AnchorRecoveryDenied, ValueError)):
        recover_forward_anchor(db, anchor, approval=approval, operator_public_key=key)
    assert not db._connection.in_transaction
    assert db._connection.execute(
        "SELECT name FROM sqlite_master WHERE name='unexpected_anchor_state'"
    ).fetchone() is None
    assert original() == (approval.candidate.next_generation, approval.candidate.next_digest)
