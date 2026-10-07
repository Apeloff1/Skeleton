from __future__ import annotations

import pytest

from skeleton.jeeves.agent.durable_transition_model import (
    DurableLearnedTransitionModel,
    DurableTransitionError,
    SQLiteTransitionJournal,
)
from skeleton.jeeves.agent.model_based_control import (
    AbstractAction,
    CompactState,
    TransitionExperience,
    TransitionOutcome,
)
from skeleton.jeeves.agent.types import RiskTier


def _experience(index: int) -> TransitionExperience:
    state = CompactState(
        state_id="state-pre",
        features={"phase": "pre"},
        progress_bucket=1,
        uncertainty_bucket=5,
        budget_bucket=1,
        failure_bucket=0,
        risk=RiskTier.READ_ONLY,
    )
    next_state = CompactState(
        state_id=f"state-post-{index}",
        features={"phase": "post"},
        progress_bucket=8,
        uncertainty_bucket=2,
        budget_bucket=2,
        failure_bucket=0,
        risk=RiskTier.READ_ONLY,
    )
    action = AbstractAction(
        action_id="action-read",
        name="tool:read_record",
        capability="read_record",
        risk=RiskTier.READ_ONLY,
    )
    return TransitionExperience(
        experience_id=f"experience-{index}",
        run_id=f"run-{index}",
        state=state,
        action=action,
        next_state=next_state,
        outcome=TransitionOutcome.SUCCESS,
        reward=0.8,
        verification_score=0.95,
        cost=0.0,
        latency_ms=5.0,
        observed_at=100.0 + index,
    )


def test_stale_second_process_cannot_fork_global_transition_model(tmp_path) -> None:
    path = tmp_path / "model.sqlite3"
    journal_a = SQLiteTransitionJournal(path)
    journal_b = SQLiteTransitionJournal(path)
    model_a = DurableLearnedTransitionModel(journal_a, model_id="global")
    model_b = DurableLearnedTransitionModel(journal_b, model_id="global")
    stale_root = model_b.fingerprint

    model_a.observe(_experience(1))
    durable_root = model_a.fingerprint
    assert durable_root != stale_root

    with pytest.raises(DurableTransitionError, match="predecessor model root conflict"):
        model_b.observe(_experience(2))

    assert model_b.fingerprint == stale_root
    rows = journal_a.entries("global")
    assert len(rows) == 1
    assert rows[0].model_fingerprint_after == durable_root

    refreshed = DurableLearnedTransitionModel(
        SQLiteTransitionJournal(path),
        model_id="global",
    )
    refreshed.observe(_experience(2))
    assert len(journal_a.entries("global")) == 2


def test_unapplied_wal_row_blocks_new_writer_until_replay_recovers_it(tmp_path) -> None:
    path = tmp_path / "model.sqlite3"
    journal = SQLiteTransitionJournal(path)
    model = DurableLearnedTransitionModel(journal, model_id="global")
    experience = _experience(1)

    pending = journal.append_pending(
        "global",
        "experience",
        {
            "model_fingerprint_before": model.fingerprint,
            "experience": DurableLearnedTransitionModel._experience_to_dict(experience),
        },
    )
    assert pending.model_fingerprint_after is None

    with pytest.raises(DurableTransitionError, match="unapplied predecessor"):
        journal.append_pending(
            "global",
            "experience",
            {
                "model_fingerprint_before": model.fingerprint,
                "experience": DurableLearnedTransitionModel._experience_to_dict(_experience(2)),
            },
        )

    recovered = DurableLearnedTransitionModel(
        SQLiteTransitionJournal(path),
        model_id="global",
    )
    assert recovered.predict("state-pre", "action-read").observations == 1
    recovered.observe(_experience(2))
    assert recovered.predict("state-pre", "action-read").observations == 2


def test_first_wal_event_requires_sha256_predecessor_root(tmp_path) -> None:
    journal = SQLiteTransitionJournal(tmp_path / "model.sqlite3")

    with pytest.raises(DurableTransitionError, match="model fingerprint must be sha256"):
        journal.append_pending(
            "global",
            "experience",
            {
                "model_fingerprint_before": "not-a-root",
                "experience": DurableLearnedTransitionModel._experience_to_dict(_experience(1)),
            },
        )

    assert journal.entries("global") == ()