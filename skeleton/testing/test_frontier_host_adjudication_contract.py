"""Host-trusted frontier candidate adjudication contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.deliberation import (
    CandidateProposal,
    SpecialistRole,
)
from skeleton.jeeves.agent.evidence import (
    EvidenceArtifact,
    EvidenceLedger,
)
from skeleton.jeeves.agent.frontier_adjudication import (
    FrontierAdjudicationPolicy,
    HostCandidateAdjudicationReport,
    HostCandidateAdjudicator,
)
from skeleton.jeeves.agent.types import (
    AgentContractError,
    EvidenceKind,
    EvidenceRef,
    stable_fingerprint,
)


def artifact(
    name: str,
    *,
    source: str = "source:a",
    confidence: float = 0.9,
    observed_at: float = 1.0,
) -> EvidenceArtifact:
    return EvidenceArtifact(
        evidence_id=f"evidence:{name}",
        kind=EvidenceKind.FIXTURE,
        source=source,
        payload={"name": name},
        observed_at=observed_at,
        confidence=confidence,
    )


def candidate(
    name: str,
    *,
    confidence: float = 0.9,
    evidence: tuple[EvidenceRef, ...] = (),
    risks: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
    depth: int = 0,
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=f"candidate:{name}",
        parent_id=None,
        depth=depth,
        role=SpecialistRole.SOLVER,
        summary=f"candidate {name}",
        proposed_action="perform bounded action",
        predicted_outcome="bounded result",
        confidence=confidence,
        evidence=evidence,
        risks=risks,
        assumptions=assumptions,
    )


def test_adjudicate_strong_diverse_evidence():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(
        artifact(
            "one",
            source="source:one",
            confidence=0.92,
        )
    )
    two = ledger.append(
        artifact(
            "two",
            source="source:two",
            confidence=0.88,
        )
    )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate(
            "strong",
            confidence=0.90,
            evidence=(one.ref, two.ref),
        )
    )
    assert result.score > 0.90
    assert result.ok
    assert not result.rejected
    assert result.custody_fraction == 1.0
    assert result.fingerprint_fraction == 1.0
    assert result.identity_fraction == 1.0
    assert result.source_diversity == 1.0
    assert result.confidence_quality == pytest.approx(0.90)
    assert result.known_evidence_count == 2
    assert result.unknown_evidence_count == 0
    assert result.total_evidence_count == 2
    assert result.contradiction_count == 0
    assert result.contradiction_rate == 0.0


def test_adjudicate_unknown_evidence_reduces_custody():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    known = ledger.append(artifact("known"))
    unknown = EvidenceRef(
        evidence_id="evidence:missing",
        kind=EvidenceKind.FIXTURE,
        source="source:missing",
        fingerprint=stable_fingerprint({"missing": True}),
        confidence=0.9,
        observed_at=1.0,
    )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate(
            "unknown",
            evidence=(known.ref, unknown),
        )
    )
    assert result.rejected
    assert result.custody_fraction == 0.5
    assert result.known_evidence_count == 1
    assert result.unknown_evidence_count == 1
    assert any(
        reason == "unknown_evidence=1"
        for reason in result.reasons
    )


def test_adjudicate_fingerprint_substitution_is_visible():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    known = ledger.append(artifact("known"))
    bad = replace(
        known.ref,
        fingerprint=stable_fingerprint({"wrong": True}),
    )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("fingerprint", evidence=(bad,))
    )
    assert result.rejected
    assert result.custody_fraction == 1.0
    assert result.fingerprint_fraction == 0.0
    assert result.fingerprint_mismatch_count == 1
    assert any(
        reason == "fingerprint_mismatch=1"
        for reason in result.reasons
    )


@pytest.mark.parametrize(
    "change",
    [
        {"source": "source:other"},
        {"kind": EvidenceKind.DERIVED},
    ],
)
def test_adjudicate_reference_identity_substitution(change):
    ledger = EvidenceLedger(clock=lambda: 10.0)
    known = ledger.append(artifact("known"))
    bad = replace(known.ref, **change)
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("identity", evidence=(bad,))
    )
    assert result.rejected
    assert result.identity_fraction == 0.0
    assert result.identity_mismatch_count == 1
    assert any(
        reason == "identity_mismatch=1"
        for reason in result.reasons
    )


def test_adjudicate_source_diversity_detects_same_source_correlation():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(
        artifact("one", source="source:shared")
    )
    two = ledger.append(
        artifact("two", source="source:shared")
    )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("same-source", evidence=(one.ref, two.ref))
    )
    assert result.source_diversity == 0.5
    assert result.custody_fraction == 1.0


def test_adjudicate_contradiction_rate_uses_possible_pairs():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(artifact("one", source="one"))
    two = ledger.append(artifact("two", source="two"))
    three = ledger.append(artifact("three", source="three"))
    ledger.mark_contradiction(
        one.evidence_id,
        two.evidence_id,
        "conflict",
    )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate(
            "three",
            evidence=(one.ref, two.ref, three.ref),
        )
    )
    assert result.contradiction_count == 1
    assert result.contradiction_rate == pytest.approx(1.0 / 3.0)
    assert result.rejected


def test_adjudicate_full_pairwise_contradictions_cap_at_one():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(artifact("one", source="one"))
    two = ledger.append(artifact("two", source="two"))
    three = ledger.append(artifact("three", source="three"))
    for left, right in (
        (one, two),
        (one, three),
        (two, three),
    ):
        ledger.mark_contradiction(
            left.evidence_id,
            right.evidence_id,
            f"{left.evidence_id}:{right.evidence_id}",
        )
    result = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate(
            "contradicted",
            evidence=(one.ref, two.ref, three.ref),
        )
    )
    assert result.contradiction_count == 3
    assert result.contradiction_rate == 1.0


def test_contradiction_penalty_is_lower_than_clean_score():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(
        artifact("one", source="one", confidence=0.95)
    )
    two = ledger.append(
        artifact("two", source="two", confidence=0.95)
    )
    target = candidate(
        "target",
        confidence=0.95,
        evidence=(one.ref, two.ref),
    )
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    clean = adjudicator.adjudicate(target)
    ledger.mark_contradiction(
        one.evidence_id,
        two.evidence_id,
        "conflict",
    )
    contradicted = adjudicator.adjudicate(target)
    assert contradicted.score < clean.score
    assert clean.score > 0.90


def test_bad_custody_scores_below_contradicted_complete_custody():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(
        artifact("one", source="one", confidence=0.95)
    )
    two = ledger.append(
        artifact("two", source="two", confidence=0.95)
    )
    target = candidate(
        "target",
        confidence=0.95,
        evidence=(one.ref, two.ref),
    )
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    ledger.mark_contradiction(
        one.evidence_id,
        two.evidence_id,
        "conflict",
    )
    contradicted = adjudicator.adjudicate(target)

    bad_ref = replace(
        one.ref,
        fingerprint=stable_fingerprint({"wrong": True}),
    )
    unknown = EvidenceRef(
        evidence_id="evidence:missing",
        kind=EvidenceKind.FIXTURE,
        source="missing",
        fingerprint=stable_fingerprint({"missing": True}),
        confidence=0.95,
        observed_at=1.0,
    )
    bad = adjudicator.adjudicate(
        candidate(
            "bad",
            confidence=0.95,
            evidence=(bad_ref, unknown),
        )
    )
    assert bad.score < contradicted.score
    assert bad.custody_fraction == 0.5
    assert bad.fingerprint_fraction == 0.0


def test_stale_evidence_is_rejected_when_age_policy_enabled():
    ledger = EvidenceLedger(clock=lambda: 100.0)
    old = ledger.append(
        artifact(
            "old",
            observed_at=1.0,
        )
    )
    policy = FrontierAdjudicationPolicy(
        maximum_evidence_age_seconds=10.0,
    )
    result = HostCandidateAdjudicator(
        ledger,
        policy=policy,
        clock=lambda: 100.0,
    ).adjudicate(
        candidate("stale", evidence=(old.ref,))
    )
    assert result.rejected
    assert result.stale_evidence_count == 1
    assert any(
        reason == "stale_evidence=1"
        for reason in result.reasons
    )


def test_future_dated_evidence_is_stale_under_age_policy():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    future = ledger.append(
        artifact(
            "future",
            observed_at=11.0,
        )
    )
    result = HostCandidateAdjudicator(
        ledger,
        policy=FrontierAdjudicationPolicy(
            maximum_evidence_age_seconds=10.0,
        ),
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("future", evidence=(future.ref,))
    )
    assert result.rejected
    assert result.stale_evidence_count == 1


def test_low_confidence_evidence_is_rejected():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    weak = ledger.append(
        artifact("weak", confidence=0.2)
    )
    result = HostCandidateAdjudicator(
        ledger,
        policy=FrontierAdjudicationPolicy(
            minimum_evidence_confidence=0.5,
        ),
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("weak", evidence=(weak.ref,))
    )
    assert result.rejected
    assert any(
        reason == "low_confidence_evidence=1"
        for reason in result.reasons
    )


def test_candidate_risk_penalty_is_preserved():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    clean = adjudicator.adjudicate(
        candidate("clean", evidence=(evidence.ref,))
    )
    risky = adjudicator.adjudicate(
        candidate(
            "risky",
            evidence=(evidence.ref,),
            risks=("risk",),
        )
    )
    assert risky.score < clean.score


def test_candidate_assumption_penalty_is_preserved():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    clean = adjudicator.adjudicate(
        candidate("clean", evidence=(evidence.ref,))
    )
    assumed = adjudicator.adjudicate(
        candidate(
            "assumed",
            evidence=(evidence.ref,),
            assumptions=("assumption",),
        )
    )
    assert assumed.score < clean.score


def test_candidate_depth_penalty_is_preserved():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    clean = adjudicator.adjudicate(
        candidate("clean", evidence=(evidence.ref,))
    )
    deep = adjudicator.adjudicate(
        candidate(
            "deep",
            evidence=(evidence.ref,),
            depth=3,
        )
    )
    assert deep.score < clean.score


def test_empty_evidence_is_fail_closed_for_host_adjudication():
    result = HostCandidateAdjudicator(
        EvidenceLedger(clock=lambda: 10.0),
        clock=lambda: 10.0,
    ).adjudicate(candidate("empty"))
    assert result.score == 0.0
    assert result.custody_fraction == 0.0
    assert result.fingerprint_fraction == 0.0
    assert result.known_evidence_count == 0
    assert result.total_evidence_count == 0


def test_reference_bound_exhaustion_is_rejected_without_ledger_reads():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    policy = FrontierAdjudicationPolicy(
        maximum_evidence_refs=1,
    )
    one = EvidenceRef(
        "evidence:one",
        EvidenceKind.FIXTURE,
        "source",
        stable_fingerprint({"one": True}),
        0.9,
        1.0,
    )
    two = EvidenceRef(
        "evidence:two",
        EvidenceKind.FIXTURE,
        "source",
        stable_fingerprint({"two": True}),
        0.9,
        1.0,
    )
    result = HostCandidateAdjudicator(
        ledger,
        policy=policy,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("bounded", evidence=(one, two))
    )
    assert result.rejected
    assert result.score == 0.0
    assert result.unknown_evidence_count == 2
    assert any(
        reason.startswith("evidence_reference_bound_exceeded=")
        for reason in result.reasons
    )


def test_invalid_clock_is_rejected():
    adjudicator = HostCandidateAdjudicator(
        EvidenceLedger(),
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        AgentContractError,
        match="clock returned invalid",
    ):
        adjudicator.adjudicate(candidate("clock"))


def test_wrong_candidate_type_is_rejected():
    adjudicator = HostCandidateAdjudicator(EvidenceLedger())
    with pytest.raises(TypeError, match="CandidateProposal"):
        adjudicator.adjudicate(object())


def test_report_fingerprint_is_stable_for_same_ledger_state():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    target = candidate(
        "stable",
        evidence=(evidence.ref,),
    )
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    first = adjudicator.adjudicate(target)
    second = adjudicator.adjudicate(target)
    assert first.fingerprint == second.fingerprint
    assert first == second


def test_report_fingerprint_changes_when_ledger_contradictions_change():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    one = ledger.append(artifact("one", source="one"))
    two = ledger.append(artifact("two", source="two"))
    target = candidate(
        "changing",
        evidence=(one.ref, two.ref),
    )
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    before = adjudicator.adjudicate(target)
    ledger.mark_contradiction(
        one.evidence_id,
        two.evidence_id,
        "conflict",
    )
    after = adjudicator.adjudicate(target)
    assert after.fingerprint != before.fingerprint


def test_report_to_dict_exposes_all_integrity_metrics():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    report = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    ).adjudicate(
        candidate("dict", evidence=(evidence.ref,))
    )
    data = report.to_dict()
    assert data["candidate_id"] == "candidate:dict"
    assert data["score"] == report.score
    assert data["custody_fraction"] == 1.0
    assert data["fingerprint_fraction"] == 1.0
    assert data["identity_fraction"] == 1.0
    assert data["source_diversity"] == 1.0
    assert data["known_evidence_count"] == 1
    assert data["unknown_evidence_count"] == 0
    assert data["total_evidence_count"] == 1
    assert data["ok"] is True
    assert len(data["fingerprint"]) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("score", -0.1),
        ("custody_fraction", 1.1),
        ("fingerprint_fraction", -0.1),
        ("identity_fraction", 1.1),
        ("source_diversity", 1.1),
        ("confidence_quality", -0.1),
        ("contradiction_rate", 1.1),
    ],
)
def test_report_probability_validation(field, value):
    values = dict(
        candidate_id="candidate",
        score=0.5,
        custody_fraction=1.0,
        fingerprint_fraction=1.0,
        identity_fraction=1.0,
        source_diversity=1.0,
        confidence_quality=0.9,
        contradiction_count=0,
        contradiction_rate=0.0,
        known_evidence_count=1,
        unknown_evidence_count=0,
        fingerprint_mismatch_count=0,
        identity_mismatch_count=0,
        stale_evidence_count=0,
        rejected=False,
        reasons=(),
        policy_fingerprint=stable_fingerprint("policy"),
        ledger_fingerprint=stable_fingerprint("ledger"),
        fingerprint=stable_fingerprint("report"),
    )
    values[field] = value
    with pytest.raises(AgentContractError):
        HostCandidateAdjudicationReport(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("contradiction_count", -1),
        ("known_evidence_count", -1),
        ("unknown_evidence_count", -1),
        ("fingerprint_mismatch_count", -1),
        ("identity_mismatch_count", -1),
        ("stale_evidence_count", -1),
    ],
)
def test_report_count_validation(field, value):
    values = dict(
        candidate_id="candidate",
        score=0.5,
        custody_fraction=1.0,
        fingerprint_fraction=1.0,
        identity_fraction=1.0,
        source_diversity=1.0,
        confidence_quality=0.9,
        contradiction_count=0,
        contradiction_rate=0.0,
        known_evidence_count=1,
        unknown_evidence_count=0,
        fingerprint_mismatch_count=0,
        identity_mismatch_count=0,
        stale_evidence_count=0,
        rejected=False,
        reasons=(),
        policy_fingerprint=stable_fingerprint("policy"),
        ledger_fingerprint=stable_fingerprint("ledger"),
        fingerprint=stable_fingerprint("report"),
    )
    values[field] = value
    with pytest.raises(AgentContractError):
        HostCandidateAdjudicationReport(**values)


def test_report_requires_candidate_id():
    with pytest.raises(AgentContractError, match="candidate_id"):
        HostCandidateAdjudicationReport(
            candidate_id="",
            score=0.5,
            custody_fraction=1.0,
            fingerprint_fraction=1.0,
            identity_fraction=1.0,
            source_diversity=1.0,
            confidence_quality=0.9,
            contradiction_count=0,
            contradiction_rate=0.0,
            known_evidence_count=1,
            unknown_evidence_count=0,
            fingerprint_mismatch_count=0,
            identity_mismatch_count=0,
            stale_evidence_count=0,
            rejected=False,
            reasons=(),
            policy_fingerprint=stable_fingerprint("policy"),
            ledger_fingerprint=stable_fingerprint("ledger"),
            fingerprint=stable_fingerprint("report"),
        )


@pytest.mark.parametrize(
    "field",
    [
        "policy_fingerprint",
        "ledger_fingerprint",
        "fingerprint",
    ],
)
def test_report_requires_digest_shaped_fingerprints(field):
    values = dict(
        candidate_id="candidate",
        score=0.5,
        custody_fraction=1.0,
        fingerprint_fraction=1.0,
        identity_fraction=1.0,
        source_diversity=1.0,
        confidence_quality=0.9,
        contradiction_count=0,
        contradiction_rate=0.0,
        known_evidence_count=1,
        unknown_evidence_count=0,
        fingerprint_mismatch_count=0,
        identity_mismatch_count=0,
        stale_evidence_count=0,
        rejected=False,
        reasons=(),
        policy_fingerprint=stable_fingerprint("policy"),
        ledger_fingerprint=stable_fingerprint("ledger"),
        fingerprint=stable_fingerprint("report"),
    )
    values[field] = "bad"
    with pytest.raises(AgentContractError, match="SHA-256"):
        HostCandidateAdjudicationReport(**values)


def test_score_callback_contract_remains_backward_compatible():
    ledger = EvidenceLedger(clock=lambda: 10.0)
    evidence = ledger.append(artifact("evidence"))
    target = candidate(
        "score-contract",
        evidence=(evidence.ref,),
    )
    adjudicator = HostCandidateAdjudicator(
        ledger,
        clock=lambda: 10.0,
    )
    assert adjudicator.score(target) == adjudicator.inspect(target).score
