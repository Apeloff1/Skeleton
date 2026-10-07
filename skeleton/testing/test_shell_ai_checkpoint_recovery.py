"""AI checkpoint, session store, and recovery tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.checkpoint import AISessionCheckpoint
from skeleton.shells.ai.journal import AIDecisionJournal
from skeleton.shells.ai.recovery import AIRecoveryManager, RecoveryAction
from skeleton.shells.ai.session import AISessionPhase, AIShellSession
from skeleton.shells.ai.session_store import AISessionConflict, AISessionStore
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal


def root(char):
    return char * 64


def session_at_review():
    session = AIShellSession("s", AIIntent("i", "do work"))
    session.transition(AISessionPhase.PLANNING)
    session.set_proposal(
        AIPlanProposal(
            "p",
            "i",
            (AIAction("a", "python"),),
            confidence=0.9,
            uncertainty=0.1,
        )
    )
    session.transition(AISessionPhase.REVIEW)
    return session


def checkpoint(session=None, **changes):
    session = session or session_at_review()
    values = dict(
        journal_root=root("a"),
        receipt_root=root("b"),
        policy_fingerprint=root("c"),
        tool_catalog_digest=root("d"),
        effect_digest=root("e"),
    )
    values.update(changes)
    return AISessionCheckpoint.capture(session, **values)


def test_checkpoint_capture_review_state():
    item = checkpoint()
    assert item.phase == "review"
    assert item.proposal_id == "p"
    assert len(item.digest) == 64


def test_checkpoint_without_proposal():
    session = AIShellSession("s", AIIntent("i", "do work"))
    item = checkpoint(session)
    assert item.proposal_id == ""
    assert item.proposal_fingerprint == ""


def test_checkpoint_rejects_bad_roots():
    with pytest.raises(ValueError):
        AISessionCheckpoint(
            1,
            "s",
            "review",
            "i",
            root("a"),
            "p",
            root("b"),
            1,
            "short",
            root("c"),
            root("d"),
            root("e"),
            root("f"),
        )


def test_session_store_first_revision():
    store = AISessionStore()
    stored = store.put(checkpoint())
    assert stored.revision == 1
    assert not stored.superseded


def test_session_store_identical_is_idempotent():
    store = AISessionStore()
    item = checkpoint()
    first = store.put(item)
    second = store.put(item)
    assert first == second


def test_session_store_changed_checkpoint_supersedes():
    store = AISessionStore()
    first = checkpoint()
    store.put(first)
    second = AISessionCheckpoint(
        first.schema_version,
        first.session_id,
        first.phase,
        first.intent_id,
        first.intent_fingerprint,
        first.proposal_id,
        first.proposal_fingerprint,
        first.transition_count,
        first.journal_root,
        root("9"),
        first.policy_fingerprint,
        first.tool_catalog_digest,
        first.effect_digest,
    )
    updated = store.put(second, expected_revision=1)
    assert updated.revision == 2
    assert store.history("s")[0].superseded


def test_session_store_conflict():
    store = AISessionStore()
    store.put(checkpoint())
    with pytest.raises(AISessionConflict):
        store.put(checkpoint(), expected_revision=0)


def test_recovery_review_can_resume():
    journal = AIDecisionJournal()
    item = checkpoint(journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=item.receipt_root,
        current_policy_fingerprint=item.policy_fingerprint,
        current_tool_catalog_digest=item.tool_catalog_digest,
        current_effect_digest=item.effect_digest,
    )
    assert report.action is RecoveryAction.RESUME_REVIEW
    assert report.safe_to_resume


def test_recovery_policy_change_requires_replan():
    journal = AIDecisionJournal()
    item = checkpoint(journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=item.receipt_root,
        current_policy_fingerprint=root("9"),
        current_tool_catalog_digest=item.tool_catalog_digest,
        current_effect_digest=item.effect_digest,
    )
    assert report.action is RecoveryAction.REQUIRE_REPLAN


def test_recovery_tool_change_requires_replan():
    journal = AIDecisionJournal()
    item = checkpoint(journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=item.receipt_root,
        current_policy_fingerprint=item.policy_fingerprint,
        current_tool_catalog_digest=root("9"),
        current_effect_digest=item.effect_digest,
    )
    assert report.action is RecoveryAction.REQUIRE_REPLAN


def test_recovery_effect_change_requires_replan():
    journal = AIDecisionJournal()
    item = checkpoint(journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=item.receipt_root,
        current_policy_fingerprint=item.policy_fingerprint,
        current_tool_catalog_digest=item.tool_catalog_digest,
        current_effect_digest=root("9"),
    )
    assert report.action is RecoveryAction.REQUIRE_REPLAN


def test_recovery_interrupted_execution_requires_verification():
    session = session_at_review()
    session.transition(AISessionPhase.APPROVED)
    session.transition(AISessionPhase.EXECUTING)
    journal = AIDecisionJournal()
    item = checkpoint(session, journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=root("9"),
        current_policy_fingerprint=item.policy_fingerprint,
        current_tool_catalog_digest=item.tool_catalog_digest,
        current_effect_digest=item.effect_digest,
    )
    assert report.action is RecoveryAction.REQUIRE_VERIFICATION


def test_recovery_tampered_journal_manual_review():
    journal = AIDecisionJournal()
    event = journal.append("x", session_id="s", intent_id="i")
    from dataclasses import replace
    journal._items[0] = replace(event, summary="tampered")
    item = checkpoint(journal_root=journal.root_hash())
    report = AIRecoveryManager().inspect(
        item,
        journal,
        current_receipt_root=item.receipt_root,
        current_policy_fingerprint=item.policy_fingerprint,
        current_tool_catalog_digest=item.tool_catalog_digest,
        current_effect_digest=item.effect_digest,
    )
    assert report.action is RecoveryAction.MANUAL_REVIEW
    assert not report.safe_to_resume
