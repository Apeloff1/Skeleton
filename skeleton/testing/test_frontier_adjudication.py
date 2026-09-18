"""Host-side frontier candidate adjudication contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.deliberation import (
    CandidateProposal,
    CandidateScorer,
    SpecialistRole,
)
from skeleton.jeeves.agent.evidence import (
    EvidenceArtifact,
    EvidenceLedger,
)
from skeleton.jeeves.agent.frontier_adjudication import (
    FrontierAdjudicationPolicy,
    FrontierAdjudicationReport,
    HostCandidateAdjudicator,
)
from skeleton.jeeves.agent.types import (
    AgentContractError,
    EvidenceKind,
    EvidenceRef,
)


def ledger(*, clock=lambda: 100.0) -> EvidenceLedger:
    return EvidenceLedger(clock=clock)


def artifact(
    evidence_id="ev-1",
    *,
    payload=None,
    source="tool:test",
    kind=EvidenceKind.TOOL,
    confidence=0.9,
    observed_at=90.0,
) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id=evidence_id,
        kind=kind,
        source=source,
        payload={"value": evidence_id} if payload is None else payload,
        observed_at=observed_at,
        confidence=confidence,
    )


def candidate(
    *,
    candidate_id="candidate-1",
    evidence=(),
    confidence=0.85,
    risks=(),
    assumptions=(),
    depth=0,
    proposed_action="inspect state",
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=candidate_id,
        parent_id=None,
        depth=depth,
        role=SpecialistRole.SOLVER,
        summary="Use trusted evidence to choose a bounded action.",
        proposed_action=proposed_action,
        predicted_outcome="The state is inspected without mutation.",
        confidence=confidence,
        evidence=tuple(evidence),
        assumptions=tuple(assumptions),
        risks=tuple(risks),
        expected_cost=0.0,
        expected_latency_ms=10.0,
    )


def adjudicator(
    item_ledger=None,
    *,
    policy=None,
    clock=lambda: 100.0,
) -> HostCandidateAdjudicator:
    return HostCandidateAdjudicator(
        item_ledger or ledger(clock=clock),
        policy=policy,
        clock=clock,
    )


def test_valid_ledger_evidence_receives_high_bounded_score():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(item.ref,))
    )

    assert not report.rejected
    assert report.matched_evidence == 1
    assert report.missing_evidence == 0
    assert report.stale_evidence == 0
    assert report.contradictions == 0
    assert 0.7 <= report.score <= 1.0
    assert 0.0 <= report.evidence_quality <= 1.0
    assert report.evidence_integrity == 1.0
    assert len(report.fingerprint) == 64


def test_score_callback_matches_report_score():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    target = adjudicator(item_ledger)
    proposal = candidate(evidence=(item.ref,))

    assert target.score(proposal) == target.inspect(proposal).score


def test_missing_evidence_fails_closed():
    item_ledger = ledger()
    missing = artifact().ref
    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(missing,))
    )

    assert report.rejected
    assert report.score == 0.0
    assert report.matched_evidence == 0
    assert report.missing_evidence == 1
    assert any("missing ledger evidence" in reason for reason in report.reasons)


def test_fingerprint_mismatch_fails_closed():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    forged = replace(item.ref, fingerprint="a" * 64)

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(forged,))
    )

    assert report.rejected
    assert report.score == 0.0
    assert any("fingerprint" in reason for reason in report.reasons)


def test_source_mismatch_fails_closed():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    forged = replace(item.ref, source="tool:other")

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(forged,))
    )

    assert report.rejected
    assert report.score == 0.0
    assert any("source" in reason for reason in report.reasons)


def test_kind_mismatch_fails_closed():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    forged = replace(item.ref, kind=EvidenceKind.API)

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(forged,))
    )

    assert report.rejected
    assert report.score == 0.0
    assert any("kind" in reason for reason in report.reasons)


def test_reference_confidence_below_floor_fails_closed():
    item_ledger = ledger()
    item = item_ledger.append(artifact(confidence=0.9))
    low = replace(item.ref, confidence=0.2)
    policy = FrontierAdjudicationPolicy(
        minimum_evidence_confidence=0.5,
    )

    report = adjudicator(
        item_ledger,
        policy=policy,
    ).inspect(candidate(evidence=(low,)))

    assert report.rejected
    assert report.score == 0.0
    assert any("confidence below" in reason for reason in report.reasons)


def test_artifact_confidence_below_floor_fails_closed():
    item_ledger = ledger()
    item = item_ledger.append(artifact(confidence=0.2))
    policy = FrontierAdjudicationPolicy(
        minimum_evidence_confidence=0.5,
    )

    report = adjudicator(
        item_ledger,
        policy=policy,
    ).inspect(candidate(evidence=(item.ref,)))

    assert report.rejected
    assert report.score == 0.0


def test_stale_evidence_fails_closed():
    item_ledger = ledger(clock=lambda: 100.0)
    item = item_ledger.append(
        artifact(observed_at=10.0)
    )
    policy = FrontierAdjudicationPolicy(
        maximum_evidence_age_seconds=20.0,
    )

    report = adjudicator(
        item_ledger,
        policy=policy,
        clock=lambda: 100.0,
    ).inspect(candidate(evidence=(item.ref,)))

    assert report.rejected
    assert report.stale_evidence == 1
    assert any("stale" in reason for reason in report.reasons)


def test_future_evidence_is_treated_as_stale_invalid_time():
    item_ledger = ledger(clock=lambda: 100.0)
    item = item_ledger.append(
        artifact(observed_at=101.0)
    )
    policy = FrontierAdjudicationPolicy(
        maximum_evidence_age_seconds=20.0,
    )

    report = adjudicator(
        item_ledger,
        policy=policy,
        clock=lambda: 100.0,
    ).inspect(candidate(evidence=(item.ref,)))

    assert report.rejected
    assert report.stale_evidence == 1


def test_no_age_policy_allows_old_evidence():
    item_ledger = ledger()
    item = item_ledger.append(
        artifact(observed_at=1.0)
    )

    report = adjudicator(
        item_ledger,
        clock=lambda: 1_000_000.0,
    ).inspect(candidate(evidence=(item.ref,)))

    assert not report.rejected
    assert report.matched_evidence == 1


def test_contradictory_evidence_fails_closed_by_default():
    item_ledger = ledger()
    left = item_ledger.append(
        artifact("left", payload={"answer": "yes"})
    )
    right = item_ledger.append(
        artifact("right", payload={"answer": "no"})
    )
    item_ledger.mark_contradiction(
        left.evidence_id,
        right.evidence_id,
        "opposed verified observations",
    )

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(left.ref, right.ref))
    )

    assert report.rejected
    assert report.score == 0.0
    assert report.contradictions == 1
    assert any("contradictory" in reason for reason in report.reasons)


def test_configured_contradiction_score_is_bounded():
    item_ledger = ledger()
    left = item_ledger.append(
        artifact("left", payload={"v": 1})
    )
    right = item_ledger.append(
        artifact("right", payload={"v": 2})
    )
    item_ledger.mark_contradiction(
        "left",
        "right",
        "conflict",
    )
    policy = FrontierAdjudicationPolicy(
        contradiction_score=0.15,
    )

    report = adjudicator(
        item_ledger,
        policy=policy,
    ).inspect(candidate(evidence=(left.ref, right.ref)))

    assert report.rejected
    assert report.score == 0.15


def test_evidence_free_candidate_gets_bounded_ungrounded_score():
    policy = FrontierAdjudicationPolicy(
        ungrounded_score=0.3,
    )
    report = adjudicator(policy=policy).inspect(candidate())

    assert not report.rejected
    assert report.score == 0.3
    assert report.matched_evidence == 0
    assert any("no ledger evidence" in reason for reason in report.reasons)


def test_evidence_free_risk_penalty_lowers_score():
    policy = FrontierAdjudicationPolicy(
        ungrounded_score=0.5,
        risk_penalty_per_item=0.1,
    )
    target = adjudicator(policy=policy)

    base = target.score(candidate())
    risky = target.score(
        candidate(
            candidate_id="risky",
            risks=("risk one", "risk two"),
        )
    )

    assert risky < base
    assert risky == pytest.approx(0.3)


def test_evidence_free_assumption_penalty_lowers_score():
    policy = FrontierAdjudicationPolicy(
        ungrounded_score=0.5,
        assumption_penalty_per_item=0.1,
    )
    target = adjudicator(policy=policy)

    assert target.score(
        candidate(
            candidate_id="assumptions",
            assumptions=("one", "two"),
        )
    ) == pytest.approx(0.3)


def test_depth_penalty_lowers_score():
    policy = FrontierAdjudicationPolicy(
        ungrounded_score=0.5,
        depth_penalty_per_level=0.1,
    )
    target = adjudicator(policy=policy)

    shallow = target.score(candidate())
    deep = target.score(
        candidate(candidate_id="deep", depth=3)
    )

    assert deep < shallow
    assert deep == pytest.approx(0.2)


def test_grounded_risk_penalty_lowers_score():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    target = adjudicator(
        item_ledger,
        policy=FrontierAdjudicationPolicy(
            risk_penalty_per_item=0.1,
        ),
    )

    safe = target.score(
        candidate(
            candidate_id="safe",
            evidence=(item.ref,),
        )
    )
    risky = target.score(
        candidate(
            candidate_id="risky",
            evidence=(item.ref,),
            risks=("one", "two"),
        )
    )

    assert risky < safe


def test_confidence_alignment_rewards_calibrated_candidate():
    item_ledger = ledger()
    item = item_ledger.append(
        artifact(confidence=0.8)
    )
    target = adjudicator(item_ledger)

    aligned = target.inspect(
        candidate(
            candidate_id="aligned",
            evidence=(item.ref,),
            confidence=0.8,
        )
    )
    overconfident = target.inspect(
        candidate(
            candidate_id="over",
            evidence=(item.ref,),
            confidence=1.0,
        )
    )

    assert aligned.confidence_alignment > overconfident.confidence_alignment
    assert aligned.score > overconfident.score


def test_multiple_valid_evidence_refs_average_quality():
    item_ledger = ledger()
    first = item_ledger.append(
        artifact(
            "first",
            payload={"v": 1},
            confidence=1.0,
        )
    )
    second = item_ledger.append(
        artifact(
            "second",
            payload={"v": 2},
            confidence=0.6,
        )
    )

    report = adjudicator(item_ledger).inspect(
        candidate(
            evidence=(first.ref, second.ref),
            confidence=0.8,
        )
    )

    assert not report.rejected
    assert report.evidence_quality == pytest.approx(0.8)
    assert report.evidence_integrity == 1.0
    assert report.matched_evidence == 2


def test_maximum_evidence_ref_bound_fails_closed():
    item_ledger = ledger()
    refs = []
    for index in range(3):
        item = item_ledger.append(
            artifact(
                f"ev-{index}",
                payload={"index": index},
            )
        )
        refs.append(item.ref)
    target = adjudicator(
        item_ledger,
        policy=FrontierAdjudicationPolicy(
            maximum_evidence_refs=2,
        ),
    )

    report = target.inspect(candidate(evidence=tuple(refs)))

    assert report.rejected
    assert report.score == 0.0
    assert report.missing_evidence == 3
    assert any("bound exceeded" in reason for reason in report.reasons)


def test_report_fingerprint_is_deterministic():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    target = adjudicator(item_ledger)
    proposal = candidate(evidence=(item.ref,))

    first = target.inspect(proposal)
    second = target.inspect(proposal)

    assert first == second
    assert first.fingerprint == second.fingerprint


def test_report_fingerprint_changes_when_ledger_changes():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    target = adjudicator(item_ledger)
    proposal = candidate(evidence=(item.ref,))
    before = target.inspect(proposal)

    item_ledger.append(
        artifact(
            "other",
            payload={"other": True},
        )
    )
    after = target.inspect(proposal)

    assert before.score == after.score
    assert before.fingerprint != after.fingerprint


def test_report_to_dict_is_json_ready():
    report = adjudicator().inspect(candidate())
    data = report.to_dict()

    assert data["candidate_id"] == "candidate-1"
    assert isinstance(data["reasons"], list)
    assert data["policy_fingerprint"]
    assert data["fingerprint"]


def test_candidate_scorer_integration_uses_host_verifier():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    host = adjudicator(item_ledger)
    scorer = CandidateScorer(verifier=host.score)

    score = scorer.score(
        candidate(evidence=(item.ref,))
    )

    assert score.verifier_score == host.score(
        candidate(evidence=(item.ref,))
    )
    assert 0.0 <= score.total <= 1.0


def test_candidate_scorer_missing_evidence_gets_zero_verifier_score():
    host = adjudicator()
    scorer = CandidateScorer(verifier=host.score)
    missing = artifact().ref

    score = scorer.score(
        candidate(evidence=(missing,))
    )

    assert score.verifier_score == 0.0


def test_wrong_candidate_type_rejected():
    with pytest.raises(TypeError, match="CandidateProposal"):
        adjudicator().inspect(object())


def test_wrong_candidate_type_score_rejected():
    with pytest.raises(TypeError, match="CandidateProposal"):
        adjudicator().score(object())


def test_wrong_ledger_type_rejected():
    with pytest.raises(TypeError, match="EvidenceLedger"):
        HostCandidateAdjudicator(object())


def test_non_callable_clock_rejected():
    with pytest.raises(TypeError, match="clock"):
        HostCandidateAdjudicator(ledger(), clock=1)


def test_invalid_clock_value_rejected_when_age_checked():
    item_ledger = ledger()
    item = item_ledger.append(artifact())
    target = adjudicator(
        item_ledger,
        policy=FrontierAdjudicationPolicy(
            maximum_evidence_age_seconds=10,
        ),
        clock=lambda: float("nan"),
    )
    with pytest.raises(AgentContractError, match="clock"):
        target.inspect(candidate(evidence=(item.ref,)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"maximum_evidence_refs": 0},
        {"maximum_evidence_refs": 4097},
        {"minimum_evidence_confidence": -0.1},
        {"minimum_evidence_confidence": 1.1},
        {"ungrounded_score": -0.1},
        {"ungrounded_score": 1.1},
        {"contradiction_score": -0.1},
        {"contradiction_score": 1.1},
        {"risk_penalty_per_item": -0.1},
        {"assumption_penalty_per_item": 1.1},
        {"depth_penalty_per_level": -0.1},
        {"maximum_evidence_age_seconds": 0},
        {"maximum_evidence_age_seconds": -1},
    ],
)
def test_adjudication_policy_validation(kwargs):
    with pytest.raises(AgentContractError):
        FrontierAdjudicationPolicy(**kwargs)


def test_adjudication_policy_requires_nonzero_quality_weights():
    with pytest.raises(AgentContractError, match="non-zero"):
        FrontierAdjudicationPolicy(
            evidence_weight=0.0,
            integrity_weight=0.0,
            calibration_weight=0.0,
            confidence_weight=0.0,
        )


def test_adjudication_policy_fingerprint_is_deterministic():
    item = FrontierAdjudicationPolicy()
    assert len(item.fingerprint) == 64
    assert item.fingerprint == item.fingerprint


def test_adjudication_policy_fingerprint_changes_with_threshold():
    first = FrontierAdjudicationPolicy()
    second = FrontierAdjudicationPolicy(
        minimum_evidence_confidence=0.5,
    )
    assert first.fingerprint != second.fingerprint


def test_report_rejects_out_of_range_score():
    with pytest.raises(AgentContractError):
        FrontierAdjudicationReport(
            "candidate",
            2.0,
            1.0,
            1.0,
            1.0,
            1,
            0,
            0,
            0,
            False,
            (),
            "p" * 64,
            "f" * 64,
        )


def test_report_rejects_negative_counts():
    with pytest.raises(AgentContractError):
        FrontierAdjudicationReport(
            "candidate",
            0.5,
            1.0,
            1.0,
            1.0,
            -1,
            0,
            0,
            0,
            False,
            (),
            "p" * 64,
            "f" * 64,
        )


def test_partial_validity_still_fails_closed_on_one_forged_ref():
    item_ledger = ledger()
    valid = item_ledger.append(
        artifact("valid", payload={"valid": True})
    )
    forged = EvidenceRef(
        evidence_id="missing",
        kind=EvidenceKind.TOOL,
        source="tool:test",
        fingerprint="b" * 64,
        confidence=1.0,
        observed_at=90.0,
    )

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(valid.ref, forged))
    )

    assert report.rejected
    assert report.score == 0.0
    assert report.matched_evidence == 1
    assert report.missing_evidence == 1


def test_candidate_reference_identity_must_match_authoritative_ledger():
    item_ledger = ledger()
    stored = item_ledger.append(
        artifact(
            "ev-1",
            source="tool:trusted",
            kind=EvidenceKind.API,
        )
    )
    forged = EvidenceRef(
        evidence_id=stored.evidence_id,
        kind=EvidenceKind.TOOL,
        source="tool:untrusted",
        fingerprint=stored.fingerprint,
        confidence=stored.confidence,
        observed_at=stored.observed_at,
    )

    report = adjudicator(item_ledger).inspect(
        candidate(evidence=(forged,))
    )

    assert report.rejected
    assert report.score == 0.0
    assert any("kind" in reason for reason in report.reasons)
    assert any("source" in reason for reason in report.reasons)
