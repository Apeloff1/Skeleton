from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from skeleton.contracts.promotion_gates import (
    GateObservation,
    PromotionGateError,
    canonical_digest,
    evaluate_required_gates,
)


HEAD = "a" * 40
STALE = "b" * 40
NOW = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
AUTHORITY_PATH = Path("machine/p1_required_gate_authority.json")


def _authority() -> dict:
    return json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))


def _observation(
    workflow_name: str,
    *,
    head_sha: str = HEAD,
    run_id: str | None = None,
    run_attempt: int = 1,
    event: str = "pull_request",
    status: str = "completed",
    conclusion: str = "success",
) -> GateObservation:
    return GateObservation(
        workflow_name=workflow_name,
        head_sha=head_sha,
        run_id=run_id or f"run:{workflow_name}",
        run_attempt=run_attempt,
        event=event,
        status=status,
        conclusion=conclusion,
        completed_at=NOW,
    )


def _passing_observations(authority: dict) -> tuple[GateObservation, ...]:
    return tuple(
        _observation(gate["workflow_name"])
        for gate in authority["gates"]
        if gate["required_for_terminal_p1_promotion"]
    )


def test_required_gate_authority_accepts_one_exact_success_per_gate() -> None:
    authority = _authority()
    decision = evaluate_required_gates(
        authority,
        _passing_observations(authority),
        target_sha=HEAD,
    )

    assert decision.accepted is True
    assert decision.required_gate_count == 22
    assert decision.passing_gate_count == 22
    assert decision.missing == ()
    assert decision.stale == ()
    assert decision.duplicate == ()
    assert decision.wrong_event == ()
    assert decision.nonterminal == ()
    assert decision.rejected == ()
    assert len(decision.authority_digest) == 64
    assert len(decision.observations_digest) == 64


def test_missing_required_gate_fails_closed() -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))
    missing = observations.pop().workflow_name

    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is False
    assert decision.missing == (missing,)
    assert decision.passing_gate_count == 21


def test_only_stale_observation_fails_closed() -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))
    target = observations[0].workflow_name
    observations[0] = _observation(target, head_sha=STALE)

    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is False
    assert decision.stale == (target,)


@pytest.mark.parametrize(
    ("status", "conclusion", "bucket"),
    (
        ("queued", "success", "nonterminal"),
        ("in_progress", "success", "nonterminal"),
        ("completed", "failure", "rejected"),
        ("completed", "cancelled", "rejected"),
        ("completed", "skipped", "rejected"),
        ("completed", "neutral", "rejected"),
        ("completed", "timed_out", "rejected"),
        ("completed", "action_required", "rejected"),
    ),
)
def test_non_success_or_nonterminal_gate_fails_closed(
    status: str,
    conclusion: str,
    bucket: str,
) -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))
    target = observations[0].workflow_name
    observations[0] = _observation(
        target,
        status=status,
        conclusion=conclusion,
    )

    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is False
    assert getattr(decision, bucket) == (target,)


def test_duplicate_exact_head_observation_fails_closed() -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))
    target = observations[0].workflow_name
    observations.append(
        _observation(target, run_id="replacement-run", run_attempt=2)
    )

    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is False
    assert decision.duplicate == (target,)


def test_wrong_event_fails_closed() -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))
    target = observations[0].workflow_name
    observations[0] = _observation(target, event="push")

    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is False
    assert decision.wrong_event == (target,)


def test_unknown_gate_is_ignored_but_cannot_substitute_for_required_gate() -> None:
    authority = _authority()
    baseline_observations = list(_passing_observations(authority))
    baseline = evaluate_required_gates(
        authority,
        baseline_observations,
        target_sha=HEAD,
    )

    observations = [*baseline_observations, _observation("Untrusted Extra Gate")]
    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )

    assert decision.accepted is True
    assert decision.passing_gate_count == 22
    assert decision.observations_digest == baseline.observations_digest

    observations = observations[1:]
    decision = evaluate_required_gates(
        authority,
        observations,
        target_sha=HEAD,
    )
    assert decision.accepted is False
    assert decision.passing_gate_count == 21


def test_observation_order_is_canonical() -> None:
    authority = _authority()
    observations = list(_passing_observations(authority))

    left = evaluate_required_gates(authority, observations, target_sha=HEAD)
    right = evaluate_required_gates(
        authority,
        list(reversed(observations)),
        target_sha=HEAD,
    )

    assert left.observations_digest == right.observations_digest
    assert left.authority_digest == right.authority_digest


def test_authority_mutation_changes_digest() -> None:
    authority = _authority()
    changed = json.loads(json.dumps(authority))
    changed["gates"][0]["purpose"] += " changed"

    assert canonical_digest(authority) != canonical_digest(changed)


def test_malformed_observation_fails_during_construction() -> None:
    with pytest.raises(PromotionGateError, match="head_sha"):
        _observation("Gate", head_sha="short")

    with pytest.raises(PromotionGateError, match="run_attempt"):
        _observation("Gate", run_attempt=0)

def test_only_accepted_decision_can_materialize_promotion_evidence() -> None:
    authority = _authority()
    accepted = evaluate_required_gates(
        authority,
        _passing_observations(authority),
        target_sha=HEAD,
    )
    evidence = accepted.accepted_evidence_ref()

    assert evidence.category == "promotion_gate_authority"
    assert evidence.digest == accepted.decision_digest
    assert len(evidence.digest) == 64
    assert accepted.as_dict()["decision_digest"] == accepted.decision_digest

    rejected_observations = list(_passing_observations(authority))
    rejected_observations.pop()
    rejected = evaluate_required_gates(
        authority,
        rejected_observations,
        target_sha=HEAD,
    )
    with pytest.raises(PromotionGateError, match="cannot become promotion evidence"):
        rejected.accepted_evidence_ref()

