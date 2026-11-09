from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.eval.failure_knowledge import (
    FailureDisposition,
    FailureKnowledgeError,
    FailureKnowledgeLedger,
    FailureKnowledgeRecord,
    FailureSourceKind,
    LearningSignal,
    LearningSignalKind,
    NonApplicabilityDecision,
    learning_signal_for,
    qualify_failure_knowledge,
)
from skeleton.eval.regression_corpus import (
    FailureClass,
    RegressionCase,
    RegressionCorpus,
    SafeOutcome,
)


def _case(
    case_id: str = "spec-game-001",
    *,
    failure_class: FailureClass = FailureClass.SPECIFICATION_GAMING,
    risk_id: str = "P1-ADVERSARIAL-spec-game-001",
    risk_digest: str = "d" * 64,
) -> RegressionCase:
    return RegressionCase(
        case_id=case_id,
        version=1,
        failure_class=failure_class,
        description=f"Regression for {case_id}.",
        source_ref=f"incident:{case_id}",
        source_digest="1" * 64,
        input_digest="2" * 64,
        expected_outcome=SafeOutcome.REJECT,
        evaluator_id="independent-regression-evaluator",
        evaluator_digest="3" * 64,
        risk_obligation_id=risk_id,
        risk_obligation_digest=risk_digest,
        tags=("failure-knowledge",),
    )


def _corpus() -> RegressionCorpus:
    return RegressionCorpus(
        corpus_id="p1-known-failures",
        version=1,
        cases=(
            _case(),
            _case(
                "reasoning-001",
                failure_class=FailureClass.REASONING_ERROR,
                risk_id="P1-RISK-reasoning-001",
                risk_digest="e" * 64,
            ),
        ),
    )


def _evidence(label: str = "incident") -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"failure://{label}",
            digest="a" * 64,
            category="failure_knowledge",
        ),
    )


def _covered(
    case: RegressionCase,
    *,
    record_id: str = "failure-001",
    sequence: int = 1,
    fingerprint: str = "b" * 64,
) -> FailureKnowledgeRecord:
    return FailureKnowledgeRecord(
        record_id=record_id,
        version=1,
        sequence=sequence,
        source_kind=FailureSourceKind.INCIDENT,
        source_ref=f"incident:{record_id}",
        source_digest="4" * 64,
        failure_class=case.failure_class,
        failure_fingerprint=fingerprint,
        summary="Known failure is covered by an immutable regression.",
        root_cause_digest="5" * 64,
        risk_obligation_id=case.risk_obligation_id,
        risk_obligation_digest=case.risk_obligation_digest,
        disposition=FailureDisposition.REGRESSION_COVERED,
        evidence_refs=_evidence(record_id),
        regression_case_id=case.case_id,
        regression_case_version=case.version,
        regression_case_digest=case.case_digest,
    )


def _non_applicable(
    *,
    sequence: int = 2,
    fingerprint: str = "c" * 64,
) -> FailureKnowledgeRecord:
    risk_id = "P1-RISK-non-applicable-001"
    risk_digest = "f" * 64
    decision = NonApplicabilityDecision(
        failure_fingerprint=fingerprint,
        risk_obligation_id=risk_id,
        risk_obligation_digest=risk_digest,
        scope_digest="6" * 64,
        reason="The failure requires a subsystem absent from this candidate.",
        reviewer_id="independent-reviewer",
        reviewer_digest="7" * 64,
        evidence_refs=_evidence("non-applicable"),
        independent=True,
    )
    return FailureKnowledgeRecord(
        record_id="failure-002",
        version=1,
        sequence=sequence,
        source_kind=FailureSourceKind.REJECTED_DESIGN,
        source_ref="design:rejected-001",
        source_digest="8" * 64,
        failure_class=FailureClass.POLICY_CONFLICT,
        failure_fingerprint=fingerprint,
        summary="Rejected design is explicitly out of scope.",
        root_cause_digest="9" * 64,
        risk_obligation_id=risk_id,
        risk_obligation_digest=risk_digest,
        disposition=FailureDisposition.NON_APPLICABLE,
        evidence_refs=_evidence("rejected-design"),
        non_applicability=decision,
    )


def _risk(
    obligation_id: str,
    obligation_digest: str,
    *,
    resolved: bool = True,
    blocking: bool = True,
    blockers: tuple[str, ...] = (),
) -> RiskBindingEvaluation:
    return RiskBindingEvaluation(
        obligation_id=obligation_id,
        obligation_digest=obligation_digest,
        resolved=resolved,
        blocking=blocking,
        severity="high",
        disposition="evidence",
        blockers=blockers,
    )


def _clean():
    corpus = _corpus()
    covered = _covered(corpus.cases[0])
    non_applicable = _non_applicable()
    ledger = FailureKnowledgeLedger(
        ledger_id="p1-failure-knowledge",
        version=1,
        records=(covered, non_applicable),
    )
    risks = {
        covered.risk_obligation_id: _risk(
            covered.risk_obligation_id,
            covered.risk_obligation_digest,
        ),
        non_applicable.risk_obligation_id: _risk(
            non_applicable.risk_obligation_id,
            non_applicable.risk_obligation_digest,
        ),
    }
    return corpus, ledger, risks


def test_clean_failure_knowledge_qualifies() -> None:
    corpus, ledger, risks = _clean()

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert len(decision.signal_digests) == len(ledger.records)
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "failure_knowledge_qualification"
    assert evidence.digest == decision.decision_digest


def test_regression_case_digest_substitution_blocks() -> None:
    corpus, ledger, risks = _clean()
    bad = replace(
        ledger.records[0],
        regression_case_digest="0" * 64,
    )
    ledger = replace(ledger, records=(bad, ledger.records[1]))

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "regression-case-digest-mismatch:failure-001" in decision.reasons


def test_regression_failure_class_must_match() -> None:
    corpus, ledger, risks = _clean()
    bad = replace(
        ledger.records[0],
        failure_class=FailureClass.REASONING_ERROR,
    )
    ledger = replace(ledger, records=(bad, ledger.records[1]))

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert "failure-class-mismatch:failure-001" in decision.reasons


def test_missing_unresolved_or_nonblocking_risk_fails() -> None:
    corpus, ledger, risks = _clean()
    covered = ledger.records[0]

    missing = dict(risks)
    missing.pop(covered.risk_obligation_id)
    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=missing,
    )
    assert decision.accepted is False
    assert "risk-evaluation-missing:failure-001" in decision.reasons

    unresolved = dict(risks)
    unresolved[covered.risk_obligation_id] = _risk(
        covered.risk_obligation_id,
        covered.risk_obligation_digest,
        resolved=False,
        blockers=("review overdue",),
    )
    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=unresolved,
    )
    assert "risk-binding-unresolved:failure-001" in decision.reasons

    nonblocking = dict(risks)
    nonblocking[covered.risk_obligation_id] = _risk(
        covered.risk_obligation_id,
        covered.risk_obligation_digest,
        blocking=False,
    )
    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=nonblocking,
    )
    assert "risk-not-blocking:failure-001" in decision.reasons


def test_risk_obligation_id_substitution_blocks() -> None:
    corpus, ledger, risks = _clean()
    covered = ledger.records[0]
    substituted = dict(risks)
    substituted[covered.risk_obligation_id] = _risk(
        "P1-RISK-substituted",
        covered.risk_obligation_digest,
    )

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=substituted,
    )

    assert decision.accepted is False
    assert "risk-obligation-id-mismatch:failure-001" in decision.reasons


def test_repeated_fingerprint_cannot_split_across_regression_targets() -> None:
    corpus = _corpus()
    fingerprint = "d" * 64
    first = _covered(
        corpus.cases[0],
        record_id="repeat-001",
        sequence=1,
        fingerprint=fingerprint,
    )
    second = _covered(
        corpus.cases[1],
        record_id="repeat-002",
        sequence=2,
        fingerprint=fingerprint,
    )
    ledger = FailureKnowledgeLedger(
        ledger_id="split-lineage",
        version=1,
        records=(first, second),
    )
    risks = {
        first.risk_obligation_id: _risk(
            first.risk_obligation_id,
            first.risk_obligation_digest,
        ),
        second.risk_obligation_id: _risk(
            second.risk_obligation_id,
            second.risk_obligation_digest,
        ),
    }

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert f"failure-lineage-conflict:{fingerprint}" in decision.reasons


def test_non_applicable_requires_independent_exact_decision() -> None:
    record = _non_applicable()
    assert record.non_applicability is not None

    with pytest.raises(
        FailureKnowledgeError,
        match="must be independent",
    ):
        replace(record.non_applicability, independent=False)

    wrong = replace(
        record.non_applicability,
        failure_fingerprint="0" * 64,
    )
    with pytest.raises(
        FailureKnowledgeError,
        match="fingerprint mismatch",
    ):
        replace(record, non_applicability=wrong)


def test_regression_and_nonapplicability_are_mutually_exclusive() -> None:
    case = _corpus().cases[0]
    covered = _covered(case)
    with pytest.raises(
        FailureKnowledgeError,
        match="cannot be non-applicable",
    ):
        replace(
            covered,
            non_applicability=NonApplicabilityDecision(
                failure_fingerprint=covered.failure_fingerprint,
                risk_obligation_id=covered.risk_obligation_id,
                risk_obligation_digest=covered.risk_obligation_digest,
                scope_digest="1" * 64,
                reason="Invalid mixed disposition.",
                reviewer_id="reviewer",
                reviewer_digest="2" * 64,
                evidence_refs=_evidence("mixed"),
            ),
        )


def test_repeated_fingerprint_cannot_have_conflicting_disposition() -> None:
    corpus = _corpus()
    covered = _covered(
        corpus.cases[0],
        fingerprint="f" * 64,
    )
    non_applicable = _non_applicable(
        sequence=2,
        fingerprint="f" * 64,
    )
    ledger = FailureKnowledgeLedger(
        ledger_id="conflicting-ledger",
        version=1,
        records=(covered, non_applicable),
    )
    risks = {
        covered.risk_obligation_id: _risk(
            covered.risk_obligation_id,
            covered.risk_obligation_digest,
        ),
        non_applicable.risk_obligation_id: _risk(
            non_applicable.risk_obligation_id,
            non_applicable.risk_obligation_digest,
        ),
    }

    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    assert (
        "failure-disposition-conflict:" + ("f" * 64)
        in decision.reasons
    )


def test_ledger_sequence_is_contiguous_and_ordered() -> None:
    corpus = _corpus()
    first = _covered(corpus.cases[0], sequence=2)
    second = _non_applicable(sequence=1)
    with pytest.raises(
        FailureKnowledgeError,
        match="contiguous and ordered",
    ):
        FailureKnowledgeLedger(
            ledger_id="bad-order",
            version=1,
            records=(first, second),
        )


def test_learning_signal_has_no_production_or_self_modify_authority() -> None:
    corpus, ledger, _ = _clean()
    signal = learning_signal_for(ledger.records[0])

    assert signal.production_authority is False
    assert signal.direct_self_modify is False
    assert (
        signal.signal_kind
        is LearningSignalKind.REGRESSION_REINFORCEMENT
    )
    assert signal.target_regression_case_digest == corpus.cases[0].case_digest

    with pytest.raises(
        FailureKnowledgeError,
        match="production authority",
    ):
        replace(signal, production_authority=True)
    with pytest.raises(
        FailureKnowledgeError,
        match="directly self-modify",
    ):
        replace(signal, direct_self_modify=True)


def test_signal_shape_cannot_mix_regression_and_nonapplicability() -> None:
    with pytest.raises(
        FailureKnowledgeError,
        match="requires only regression case digest",
    ):
        LearningSignal(
            record_digest="1" * 64,
            failure_fingerprint="2" * 64,
            risk_obligation_digest="3" * 64,
            signal_kind=LearningSignalKind.REGRESSION_REINFORCEMENT,
            target_regression_case_digest="4" * 64,
            non_applicability_digest="5" * 64,
        )


def test_rejected_failure_knowledge_cannot_materialize_evidence() -> None:
    corpus, ledger, risks = _clean()
    risks = dict(risks)
    risks.pop(ledger.records[0].risk_obligation_id)
    decision = qualify_failure_knowledge(
        ledger=ledger,
        regression_corpus=corpus,
        risk_evaluations=risks,
    )

    assert decision.accepted is False
    with pytest.raises(
        FailureKnowledgeError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()


def test_learning_signal_identity_uses_shared_canonical_contract_bytes() -> None:
    signal = LearningSignal(
        record_digest="1" * 64,
        failure_fingerprint="2" * 64,
        risk_obligation_digest="3" * 64,
        signal_kind=LearningSignalKind.REGRESSION_REINFORCEMENT,
        target_regression_case_digest="4" * 64,
        non_applicability_digest=None,
    )

    assert signal.signal_digest == hashlib.sha256(
        canonical_json_bytes(signal.payload())
    ).hexdigest()


def test_failure_knowledge_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/eval/failure_knowledge.py"
    mirror = root / "skeleton/ai/evaluation/failure_knowledge.py"

    assert source.read_bytes() == mirror.read_bytes()
