from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skeleton/ai/specialization/domain_registry.py"
SPEC = importlib.util.spec_from_file_location("vol071_domain_registry_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

DomainRegistry = MODULE.DomainRegistry
EvaluationOwnership = MODULE.EvaluationOwnership
DomainProfile = MODULE.DomainProfile
SpecialistCandidate = MODULE.SpecialistCandidate
SpecialistEvaluation = MODULE.SpecialistEvaluation
RoutingDecision = MODULE.RoutingDecision
SpecializationError = MODULE.SpecializationError

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
MANIFEST = ROOT / "machine/ai_domain_registry.json"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def registry() -> DomainRegistry:
    return DomainRegistry.from_manifest(MANIFEST)


def candidate(
    specialist_id: str = "specialist-alpha",
    *,
    domain_id: str = "software-engineering",
    source_types: tuple[str, ...] = ("repository-state", "test-evidence"),
    available_tools: tuple[str, ...] = ("repository-read", "test-runner"),
    declared_assumptions: tuple[str, ...] = (),
    confidence: float = 0.9,
) -> SpecialistCandidate:
    return SpecialistCandidate(
        specialist_id=specialist_id,
        domain_id=domain_id,
        source_types=source_types,
        available_tools=available_tools,
        declared_assumptions=declared_assumptions,
        confidence=confidence,
    )


def evaluation(
    specialist_id: str = "specialist-alpha",
    *,
    domain_id: str = "software-engineering",
    owner_id: str = "eval-software-quality",
    suite_id: str = "software-specialist-v1",
    evaluated_at: datetime = NOW - timedelta(hours=1),
    quality_score: float = 0.91,
    calibration_score: float = 0.89,
) -> SpecialistEvaluation:
    return SpecialistEvaluation(
        specialist_id=specialist_id,
        domain_id=domain_id,
        owner_id=owner_id,
        suite_id=suite_id,
        evaluated_at=evaluated_at.isoformat(),
        quality_score=quality_score,
        calibration_score=calibration_score,
        evidence_digest=digest(specialist_id),
    )


def test_manifest_loads_canonical_domains() -> None:
    loaded = registry()
    assert loaded.domain_ids == (
        "research-synthesis",
        "simulation-intelligence",
        "software-engineering",
    )
    assert len(loaded.registry_digest) == 64


def test_eligible_specialist_is_selected() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation()],
        now=NOW,
    )
    assert route.decision is RoutingDecision.SPECIALIST
    assert route.selected_specialist_id == "specialist-alpha"
    registry().verify(route)


def test_unknown_domain_falls_back_to_general_capability() -> None:
    route = registry().route("unknown-domain", [], [], now=NOW)
    assert route.decision is RoutingDecision.GENERAL_FALLBACK
    assert route.selected_specialist_id is None
    registry().verify(route)


def test_out_of_domain_candidate_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(domain_id="research-synthesis")],
        [evaluation()],
        now=NOW,
    )
    assert route.decision is RoutingDecision.GENERAL_FALLBACK
    assert "out-of-domain" in route.rejection_details[0].reasons


def test_missing_required_source_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(source_types=("repository-state",))],
        [evaluation()],
        now=NOW,
    )
    assert "missing-required-sources" in route.rejection_details[0].reasons


def test_missing_required_tool_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(available_tools=("repository-read",))],
        [evaluation()],
        now=NOW,
    )
    assert "missing-required-tools" in route.rejection_details[0].reasons


def test_undeclared_tool_surface_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [
            candidate(
                available_tools=("repository-read", "test-runner", "source-search")
            )
        ],
        [evaluation()],
        now=NOW,
    )
    assert "undeclared-tool-surface" in route.rejection_details[0].reasons


def test_forbidden_assumption_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(declared_assumptions=("tests-pass-without-evidence",))],
        [evaluation()],
        now=NOW,
    )
    assert "forbidden-assumption" in route.rejection_details[0].reasons


def test_insufficient_confidence_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(confidence=0.71)],
        [evaluation()],
        now=NOW,
    )
    assert "insufficient-specialist-confidence" in route.rejection_details[0].reasons


def test_missing_evaluation_falls_back() -> None:
    route = registry().route("software-engineering", [candidate()], [], now=NOW)
    assert "missing-evaluation" in route.rejection_details[0].reasons


def test_stale_evaluation_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation(evaluated_at=NOW - timedelta(days=8))],
        now=NOW,
    )
    assert "stale-evaluation" in route.rejection_details[0].reasons


def test_future_evaluation_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation(evaluated_at=NOW + timedelta(seconds=6))],
        now=NOW,
    )
    assert "evaluation-from-future" in route.rejection_details[0].reasons


def test_wrong_eval_owner_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation(owner_id="eval-research-quality")],
        now=NOW,
    )
    assert "evaluation-owner-mismatch" in route.rejection_details[0].reasons


def test_wrong_eval_suite_falls_back() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation(suite_id="research-specialist-v1")],
        now=NOW,
    )
    assert "evaluation-suite-mismatch" in route.rejection_details[0].reasons


def test_quality_threshold_is_non_compensable() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(confidence=1.0)],
        [evaluation(quality_score=0.81, calibration_score=1.0)],
        now=NOW,
    )
    assert "quality-below-threshold" in route.rejection_details[0].reasons
    assert route.decision is RoutingDecision.GENERAL_FALLBACK


def test_calibration_threshold_is_non_compensable() -> None:
    route = registry().route(
        "software-engineering",
        [candidate(confidence=1.0)],
        [evaluation(quality_score=1.0, calibration_score=0.77)],
        now=NOW,
    )
    assert "calibration-below-threshold" in route.rejection_details[0].reasons


def test_specialist_cannot_self_own_evaluation() -> None:
    with pytest.raises(SpecializationError, match="self-own"):
        evaluation(owner_id="specialist-alpha")


def test_best_eligible_candidate_wins_deterministically() -> None:
    candidates = [
        candidate("specialist-beta", confidence=0.99),
        candidate("specialist-alpha", confidence=0.80),
    ]
    evaluations = [
        evaluation("specialist-beta", quality_score=0.9, calibration_score=0.88),
        evaluation("specialist-alpha", quality_score=0.94, calibration_score=0.86),
    ]
    first = registry().route("software-engineering", candidates, evaluations, now=NOW)
    second = registry().route(
        "software-engineering",
        tuple(reversed(candidates)),
        tuple(reversed(evaluations)),
        now=NOW,
    )
    assert first.selected_specialist_id == "specialist-alpha"
    assert first.to_wire() == second.to_wire()


def test_tie_breaks_by_specialist_identity() -> None:
    candidates = [candidate("specialist-beta"), candidate("specialist-alpha")]
    evaluations = [evaluation("specialist-beta"), evaluation("specialist-alpha")]
    route = registry().route("software-engineering", candidates, evaluations, now=NOW)
    assert route.selected_specialist_id == "specialist-alpha"


def test_duplicate_candidate_identity_fails_closed() -> None:
    with pytest.raises(SpecializationError, match="duplicate specialist"):
        registry().route(
            "software-engineering",
            [candidate(), candidate()],
            [evaluation()],
            now=NOW,
        )


def test_duplicate_evaluation_identity_fails_closed() -> None:
    with pytest.raises(SpecializationError, match="duplicate evaluation"):
        registry().route(
            "software-engineering",
            [candidate()],
            [evaluation(), evaluation()],
            now=NOW,
        )


def test_receipt_tampering_is_detected() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation()],
        now=NOW,
    )
    forged = replace(route, receipt_digest="0" * 64)
    with pytest.raises(SpecializationError, match="integrity"):
        registry().verify(forged)


def test_registry_drift_invalidates_receipt() -> None:
    route = registry().route(
        "software-engineering",
        [candidate()],
        [evaluation()],
        now=NOW,
    )
    tiny = DomainRegistry(
        [
            DomainProfile(
                domain_id="software-engineering",
                description="different contract",
                required_source_types=("repository-state", "test-evidence"),
                required_tools=("repository-read", "test-runner"),
                allowed_tools=("repository-read", "repository-write", "test-runner"),
                forbidden_assumptions=("tests-pass-without-evidence",),
                evaluation=EvaluationOwnership(
                    owner_id="eval-software-quality",
                    suite_id="software-specialist-v1",
                    min_quality_score=0.82,
                    min_calibration_score=0.78,
                    min_specialist_confidence=0.72,
                    max_age_seconds=604800,
                ),
            )
        ]
    )
    with pytest.raises(SpecializationError, match="registry digest"):
        tiny.verify(route)


def test_noncanonical_evidence_digest_is_rejected() -> None:
    with pytest.raises(SpecializationError, match="canonical sha256"):
        SpecialistEvaluation(
            specialist_id="specialist-alpha",
            domain_id="software-engineering",
            owner_id="eval-software-quality",
            suite_id="software-specialist-v1",
            evaluated_at=NOW.isoformat(),
            quality_score=0.9,
            calibration_score=0.9,
            evidence_digest="A" * 64,
        )


def test_required_tools_must_be_allowed() -> None:
    with pytest.raises(SpecializationError, match="subset"):
        DomainProfile(
            domain_id="bad-domain",
            description="bad domain",
            required_source_types=("repository-state",),
            required_tools=("test-runner",),
            allowed_tools=("repository-read",),
            forbidden_assumptions=(),
            evaluation=EvaluationOwnership(
                owner_id="eval-owner",
                suite_id="eval-suite",
                min_quality_score=0.8,
                min_calibration_score=0.8,
                min_specialist_confidence=0.8,
                max_age_seconds=60,
            ),
        )
