from __future__ import annotations

import json
import sqlite3

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


def _state(state_id: str, value: str, *, terminal: bool = False) -> CompactState:
    return CompactState(
        state_id=state_id,
        features={"phase": value, "tool": "read_record"},
        progress_bucket=2 if value == "pre" else 8,
        uncertainty_bucket=4,
        budget_bucket=1,
        failure_bucket=0,
        risk=RiskTier.READ_ONLY,
        terminal=terminal,
    )


def _action() -> AbstractAction:
    return AbstractAction(
        action_id="action-read-record",
        name="tool:read_record",
        capability="read_record",
        risk=RiskTier.READ_ONLY,
        reversible=True,
    )


def _experience(index: int, *, next_state_id: str | None = None) -> TransitionExperience:
    pre = _state("state-pre", "pre")
    next_id = next_state_id or f"state-post-{index}"
    post = _state(next_id, "post", terminal=index == 3)
    return TransitionExperience(
        experience_id=f"experience-{index}",
        run_id=f"run-{index}",
        state=pre,
        action=_action(),
        next_state=post,
        outcome=TransitionOutcome.SUCCESS,
        reward=0.7 + index * 0.01,
        verification_score=0.9,
        cost=0.01 * index,
        latency_ms=10.0 + index,
        observed_at=100.0 + index,
        evidence_ids=(f"evidence-{index}",),
        metadata={"index": index},
    )


def test_model_reconstructs_exact_fingerprint_after_restart(tmp_path) -> None:
    journal = SQLiteTransitionJournal(tmp_path / "model.sqlite3")
    first = DurableLearnedTransitionModel(journal, model_id="model-a")

    first.observe(_experience(1, next_state_id="state-post-a"))
    first.observe(_experience(2, next_state_id="state-post-b"))
    first.record_prediction_error(
        "state-pre",
        "action-read-record",
        predicted_next="state-post-a",
        actual_next="state-post-b",
    )
    expected = first.fingerprint
    expected_prediction = first.predict("state-pre", "action-read-record")

    reopened_journal = SQLiteTransitionJournal(tmp_path / "model.sqlite3")
    restored = DurableLearnedTransitionModel(
        reopened_journal,
        model_id="model-a",
    )

    assert restored.fingerprint == expected
    actual_prediction = restored.predict("state-pre", "action-read-record")
    assert actual_prediction == expected_prediction
    assert len(reopened_journal.verify("model-a")) == 3


def test_committed_but_unapplied_experience_is_recovered_on_restart(tmp_path) -> None:
    journal = SQLiteTransitionJournal(tmp_path / "model.sqlite3")
    empty = DurableLearnedTransitionModel(journal, model_id="model-crash")
    experience = _experience(1)

    pending = journal.append_pending(
        "model-crash",
        "experience",
        {
            "model_fingerprint_before": empty.fingerprint,
            "experience": DurableLearnedTransitionModel._experience_to_dict(experience),
        },
    )
    assert pending.model_fingerprint_after is None
    assert empty.predict("state-pre", "action-read-record").observations == 0

    restored = DurableLearnedTransitionModel(journal, model_id="model-crash")

    prediction = restored.predict("state-pre", "action-read-record")
    assert prediction.observations == 1
    rows = journal.entries("model-crash")
    assert rows[0].model_fingerprint_after == restored.fingerprint


def test_journal_predecessor_root_prevents_duplicate_or_reordered_learning(tmp_path) -> None:
    journal = SQLiteTransitionJournal(tmp_path / "model.sqlite3")
    model = DurableLearnedTransitionModel(journal, model_id="model-order")
    model.observe(_experience(1))

    # The public append boundary is itself fail-closed: a stale or forged
    # predecessor root must never enter the durable journal. Replay therefore
    # starts from a journal whose predecessor chain was valid at commit time.
    with pytest.raises(DurableTransitionError, match="predecessor model root conflict"):
        journal.append_pending(
            "model-order",
            "experience",
            {
                "model_fingerprint_before": "0" * 64,
                "experience": DurableLearnedTransitionModel._experience_to_dict(_experience(2)),
            },
        )

    assert len(journal.entries("model-order")) == 1
    restored = DurableLearnedTransitionModel(journal, model_id="model-order")
    assert restored.fingerprint == model.fingerprint


def test_direct_sql_payload_tamper_breaks_journal_hash(tmp_path) -> None:
    path = tmp_path / "model.sqlite3"
    journal = SQLiteTransitionJournal(path)
    model = DurableLearnedTransitionModel(journal, model_id="model-tamper")
    model.observe(_experience(1))

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM jeeves_transition_journal WHERE model_id=? AND sequence=1",
            ("model-tamper",),
        ).fetchone()
        payload = json.loads(row[0])
        payload["experience"]["reward"] = -0.99
        conn.execute(
            "UPDATE jeeves_transition_journal SET payload_json=? WHERE model_id=? AND sequence=1",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                "model-tamper",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DurableTransitionError, match="event hash mismatch"):
        journal.verify("model-tamper")


def test_record_prediction_error_is_itself_write_ahead_durable(tmp_path) -> None:
    path = tmp_path / "model.sqlite3"
    journal = SQLiteTransitionJournal(path)
    model = DurableLearnedTransitionModel(journal, model_id="model-error")
    model.observe(_experience(1, next_state_id="state-post-a"))
    before = model.fingerprint

    model.record_prediction_error(
        "state-pre",
        "action-read-record",
        predicted_next="state-post-z",
        actual_next="state-post-a",
    )
    after = model.fingerprint

    assert after != before
    rows = journal.entries("model-error")
    assert rows[-1].kind == "prediction_error"
    assert rows[-1].payload["model_fingerprint_before"] == before
    assert rows[-1].model_fingerprint_after == after
    restored = DurableLearnedTransitionModel(
        SQLiteTransitionJournal(path),
        model_id="model-error",
    )
    assert restored.fingerprint == after