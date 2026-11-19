"""No-output retirement preserves replay fences and never manufactures results."""
from dataclasses import replace

import pytest

from skeleton.ai.model_runtime.fair_stream_execution_journal import ExecutionOutcomeUnknown
from skeleton.ai.model_runtime.fair_stream_recovery import (
    RecoveryAuthorizationDenied, issue_abandonment_authorization,
    issue_recovery_authorization, verify_abandonment_authorization,
)
from skeleton.ai.model_runtime.fair_stream_session import DurableFairStreamSession, CustodyQuarantined
from skeleton.testing.test_fair_stream_session import SimulatedIndependentWatermark, store, request, budget
from skeleton.testing.test_fair_stream_execution_journal import journal, permit


@pytest.mark.parametrize("started", [False, True])
def test_tombstone_is_idempotent_and_never_a_successful_result(started):
    db = journal()
    p = permit()
    if started:
        db.begin(p)
    signed = db.record_abandonment(p, evidence_digest="a" * 64)
    assert signed["schema"] == "skeleton.ai.fair-stream-abandonment.v1"
    assert db.record_abandonment(p, evidence_digest="a" * 64) == signed
    with pytest.raises(ExecutionOutcomeUnknown):
        db.record_abandonment(p, evidence_digest="b" * 64)
    with pytest.raises(ExecutionOutcomeUnknown):
        db.begin(replace(p, lease_id="f" * 64))
    with pytest.raises(ExecutionOutcomeUnknown):
        db.commit(p, consumed_tokens=1, result_digest="e" * 64)
    with pytest.raises(ExecutionOutcomeUnknown, match="no committed"):
        db.recover_committed_receipt(p)


def test_abandonment_retires_pending_request_and_preserves_other_work():
    anchor = SimulatedIndependentWatermark()
    session = DurableFairStreamSession.bootstrap(store(), anchor)
    session.submit(request())
    session.submit(replace(request(), request_id="r2"))
    permits, prior = session.plan(budget())
    p = permits[0]
    db = journal()
    signed = db.record_abandonment(p, evidence_digest="a" * 64)
    state = session.abandon(signed)
    assert not state["checkpoint"]["pending"]
    assert len(state["checkpoint"]["requests"]) == 1
    assert state["checkpoint"]["requests"][0]["request_id"] != p.request_id
    assert anchor.read() == (state["generation"], state["digest"])
    with pytest.raises(CustodyQuarantined):
        session.abandon(signed)


def test_completion_approval_cannot_authorize_abandonment():
    p = permit()
    key = b"k" * 32
    kwargs = dict(recovery_key=key, session_id="a" * 32, generation=p.generation,
                  checkpoint_digest=p.checkpoint_digest, lease_id=p.lease_id, nonce="b" * 32)
    state = {k: kwargs[k] for k in ("session_id", "generation", "checkpoint_digest")}
    completed = issue_recovery_authorization(**kwargs)
    with pytest.raises(RecoveryAuthorizationDenied, match="distinct"):
        verify_abandonment_authorization(completed, recovery_key=key, state=state, lease_id=p.lease_id)
    approval = issue_abandonment_authorization(**kwargs, evidence_digest="a" * 64)
    verify_abandonment_authorization(approval, recovery_key=key, state=state, lease_id=p.lease_id)
    with pytest.raises(RecoveryAuthorizationDenied):
        verify_abandonment_authorization(replace(approval, evidence_digest="b" * 64),
                                         recovery_key=key, state=state, lease_id=p.lease_id)


def test_abandonment_cannot_replace_committed_result():
    db = journal()
    p = permit()
    db.begin(p)
    result = db.commit(p, consumed_tokens=1, result_digest="e" * 64)
    with pytest.raises(ExecutionOutcomeUnknown, match="existing"):
        db.record_abandonment(p, evidence_digest="a" * 64)
    assert db.recover_committed_receipt(p) == result

def test_abandonment_cannot_replace_cancelled_identity():
    db = journal()
    p = permit()
    cancelled = db.fence_unstarted(p)
    with pytest.raises(ExecutionOutcomeUnknown, match="cancellation"):
        db.record_abandonment(p, evidence_digest="a" * 64)
    assert db.recover_cancelled_receipt(p) == cancelled


def test_abandonment_rejects_forged_receipt_without_mutating_store():
    anchor = SimulatedIndependentWatermark()
    db = store()
    session = DurableFairStreamSession.bootstrap(db, anchor)
    session.submit(request())
    permits, prior = session.plan(budget())
    signed = journal().record_abandonment(permits[0], evidence_digest="a" * 64)
    forged = {**signed, "evidence_digest": "b" * 64}
    with pytest.raises(CustodyQuarantined):
        session.abandon(forged)
    assert db.load(expected_generation=prior["generation"], expected_digest=prior["digest"]).export() == prior
    assert anchor.read() == (prior["generation"], prior["digest"])
