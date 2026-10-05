from __future__ import annotations

import pytest

from skeleton.automation import technology_radar as compatibility
from skeleton.contracts import technology_radar as canonical
from skeleton.contracts.technology_radar import (
    ArchitectureDecision,
    EvidenceKind,
    RadarDecision,
    RadarError,
    RadarState,
    TechnologyCandidate,
    TechnologyEvidence,
    TechnologyExitCriteria,
    TechnologyRadar,
    technology_evidence_set_digest,
)


ARTIFACT = "1" * 64


def candidate(
    *,
    technology_id: str = "TECH.1",
    budget: int = 80,
    max_cost: int = 100,
    max_risk: int = 5,
    decision_tick: int = 20,
) -> TechnologyCandidate:
    return TechnologyCandidate(
        technology_id,
        "evaluate deterministic store",
        "BASELINE.1",
        "OWNER.ARCH",
        budget,
        decision_tick,
        TechnologyExitCriteria(max_cost, max_risk, decision_tick),
    )


def evidence(
    subject: TechnologyCandidate,
    evidence_id: str,
    kind: EvidenceKind,
    *,
    observed_tick: int = 2,
    passed: bool = True,
    metric_value: int | None = None,
    candidate_digest: str | None = None,
) -> TechnologyEvidence:
    return TechnologyEvidence(
        evidence_id=evidence_id,
        technology_id=subject.technology_id,
        candidate_digest=candidate_digest or subject.digest,
        kind=kind,
        observed_tick=observed_tick,
        passed=passed,
        artifact_digest=ARTIFACT,
        metric_value=metric_value,
    )


def adoption_evidence(
    subject: TechnologyCandidate,
    *,
    cost: int = 70,
    risk: int = 3,
    observed_tick: int = 2,
) -> tuple[TechnologyEvidence, ...]:
    return (
        evidence(
            subject,
            "EVID.FUNCTIONAL",
            EvidenceKind.FUNCTIONAL,
            observed_tick=observed_tick,
        ),
        evidence(
            subject,
            "EVID.COST",
            EvidenceKind.COST,
            observed_tick=observed_tick,
            metric_value=cost,
        ),
        evidence(
            subject,
            "EVID.RISK",
            EvidenceKind.RISK,
            observed_tick=observed_tick,
            metric_value=risk,
        ),
    )


def architecture_decision(
    subject: TechnologyCandidate,
    items: tuple[TechnologyEvidence, ...],
    *,
    decision_id: str = "ADR.1",
    observed_tick: int = 2,
    approved: bool = True,
    owner_id: str = "OWNER.ARCH",
) -> ArchitectureDecision:
    return ArchitectureDecision(
        decision_id=decision_id,
        technology_id=subject.technology_id,
        candidate_digest=subject.digest,
        evidence_set_digest=technology_evidence_set_digest(items),
        owner_id=owner_id,
        observed_tick=observed_tick,
        approved=approved,
    )


def radar_ready_for_adoption(
    *,
    subject: TechnologyCandidate | None = None,
    cost: int = 70,
    risk: int = 3,
    observed_tick: int = 2,
) -> tuple[
    TechnologyCandidate,
    tuple[TechnologyEvidence, ...],
    ArchitectureDecision,
    TechnologyRadar,
]:
    subject = subject or candidate()
    items = adoption_evidence(
        subject,
        cost=cost,
        risk=risk,
        observed_tick=observed_tick,
    )
    adr = architecture_decision(
        subject,
        items,
        observed_tick=observed_tick,
    )
    radar = TechnologyRadar((subject,), items, (adr,))
    return subject, items, adr, radar


def adopt(
    radar: TechnologyRadar,
    subject: TechnologyCandidate,
    items: tuple[TechnologyEvidence, ...],
    adr: ArchitectureDecision,
    *,
    experiment_tick: int = 1,
    adoption_tick: int = 2,
) -> None:
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        experiment_tick,
    )
    radar.decide(
        RadarDecision(
            subject.technology_id,
            RadarState.ADOPTED,
            tuple(item.evidence_id for item in items),
            adr.decision_id,
        ),
        adoption_tick,
    )


def test_automation_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_candidate_must_experiment_before_adoption() -> None:
    subject, items, adr, radar = radar_ready_for_adoption()
    with pytest.raises(RadarError, match="transition"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_adoption_requires_evidence_and_architecture_decision() -> None:
    with pytest.raises(RadarError, match="requires evidence"):
        RadarDecision("TECH.1", RadarState.ADOPTED, (), None)


def test_valid_evidence_gated_experiment_can_be_adopted() -> None:
    subject, items, adr, radar = radar_ready_for_adoption()
    adopt(radar, subject, items, adr)
    assert radar.state(subject.technology_id) is RadarState.ADOPTED
    assert len(radar.transitions) == 2
    assert radar.transitions[0].from_state is RadarState.CANDIDATE
    assert radar.transitions[0].to_state is RadarState.EXPERIMENT
    assert radar.transitions[1].from_state is RadarState.EXPERIMENT
    assert radar.transitions[1].to_state is RadarState.ADOPTED


def test_stale_experiment_cannot_become_permanent() -> None:
    subject, items, adr, radar = radar_ready_for_adoption()
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="horizon expired"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            21,
        )


def test_adoption_requires_functional_cost_and_risk_evidence() -> None:
    subject = candidate()
    functional = evidence(
        subject,
        "EVID.FUNCTIONAL",
        EvidenceKind.FUNCTIONAL,
    )
    cost = evidence(
        subject,
        "EVID.COST",
        EvidenceKind.COST,
        metric_value=70,
    )
    items = (functional, cost)
    adr = architecture_decision(subject, items)
    radar = TechnologyRadar((subject,), items, (adr,))
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="missing required evidence kinds"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_failed_evidence_cannot_authorize_adoption() -> None:
    subject = candidate()
    items = list(adoption_evidence(subject))
    items[0] = evidence(
        subject,
        "EVID.FUNCTIONAL",
        EvidenceKind.FUNCTIONAL,
        passed=False,
    )
    selected = tuple(items)
    adr = architecture_decision(subject, selected)
    radar = TechnologyRadar((subject,), selected, (adr,))
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="failed evidence"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in selected),
                adr.decision_id,
            ),
            2,
        )


def test_future_evidence_cannot_authorize_adoption() -> None:
    subject, items, adr, radar = radar_ready_for_adoption(
        observed_tick=5,
    )
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="future evidence"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_adoption_rejects_unknown_evidence_reference() -> None:
    subject, items, adr, radar = radar_ready_for_adoption()
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="unknown evidence"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                ("EVID.MISSING",),
                adr.decision_id,
            ),
            2,
        )


def test_foreign_technology_evidence_cannot_be_reused() -> None:
    first = candidate(technology_id="TECH.1")
    second = TechnologyCandidate(
        "TECH.2",
        "evaluate second technology",
        "BASELINE.1",
        "OWNER.ARCH",
        80,
        20,
        TechnologyExitCriteria(100, 5, 20),
    )
    foreign = evidence(
        second,
        "EVID.FOREIGN",
        EvidenceKind.FUNCTIONAL,
    )
    radar = TechnologyRadar((first, second), (foreign,))
    radar.decide(
        RadarDecision(first.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="foreign technology evidence"):
        radar.decide(
            RadarDecision(
                first.technology_id,
                RadarState.ADOPTED,
                ("EVID.FOREIGN",),
                "ADR.MISSING",
            ),
            2,
        )


def test_evidence_must_bind_exact_candidate_revision() -> None:
    subject = candidate()
    stale = evidence(
        subject,
        "EVID.STALE",
        EvidenceKind.FUNCTIONAL,
        candidate_digest="0" * 64,
    )
    with pytest.raises(RadarError, match="candidate digest mismatch"):
        TechnologyRadar((subject,), (stale,))


def test_cost_above_exit_ceiling_blocks_adoption() -> None:
    subject, items, adr, radar = radar_ready_for_adoption(
        subject=candidate(budget=80, max_cost=100),
        cost=101,
    )
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="exit cost threshold"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_cost_above_experiment_budget_blocks_adoption() -> None:
    subject, items, adr, radar = radar_ready_for_adoption(
        subject=candidate(budget=60, max_cost=100),
        cost=70,
    )
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="candidate budget"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_risk_above_exit_threshold_blocks_adoption() -> None:
    subject, items, adr, radar = radar_ready_for_adoption(risk=6)
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="risk threshold"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_architecture_decision_must_bind_exact_evidence_set() -> None:
    subject = candidate()
    items = adoption_evidence(subject)
    adr = ArchitectureDecision(
        "ADR.1",
        subject.technology_id,
        subject.digest,
        "0" * 64,
        subject.owner_id,
        2,
        True,
    )
    radar = TechnologyRadar((subject,), items, (adr,))
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="evidence set mismatch"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_rejected_architecture_decision_cannot_promote() -> None:
    subject = candidate()
    items = adoption_evidence(subject)
    adr = architecture_decision(subject, items, approved=False)
    radar = TechnologyRadar((subject,), items, (adr,))
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="rejected adoption"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_future_architecture_decision_cannot_promote() -> None:
    subject = candidate()
    items = adoption_evidence(subject)
    adr = architecture_decision(
        subject,
        items,
        observed_tick=5,
    )
    radar = TechnologyRadar((subject,), items, (adr,))
    radar.decide(
        RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
        1,
    )
    with pytest.raises(RadarError, match="future"):
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.ADOPTED,
                tuple(item.evidence_id for item in items),
                adr.decision_id,
            ),
            2,
        )


def test_architecture_decision_owner_must_match_candidate_owner() -> None:
    subject = candidate()
    items = adoption_evidence(subject)
    adr = architecture_decision(
        subject,
        items,
        owner_id="OWNER.OTHER",
    )
    with pytest.raises(RadarError, match="owner mismatch"):
        TechnologyRadar((subject,), items, (adr,))


def test_adopted_technology_retirement_requires_retirement_evidence() -> None:
    subject, items, adr, radar = radar_ready_for_adoption()
    adopt(radar, subject, items, adr)
    with pytest.raises(RadarError, match="retirement requires"):
        radar.decide(
            RadarDecision(subject.technology_id, RadarState.RETIRED, ()),
            3,
        )


def test_retirement_has_explicit_evidence_path_even_after_horizon() -> None:
    subject = candidate()
    adopt_items = adoption_evidence(subject)
    retirement = evidence(
        subject,
        "EVID.RETIRE",
        EvidenceKind.RETIREMENT,
        observed_tick=25,
    )
    adr = architecture_decision(subject, adopt_items)
    radar = TechnologyRadar(
        (subject,),
        adopt_items + (retirement,),
        (adr,),
    )
    adopt(radar, subject, adopt_items, adr)
    assert (
        radar.decide(
            RadarDecision(
                subject.technology_id,
                RadarState.RETIRED,
                (retirement.evidence_id,),
            ),
            25,
        )
        is RadarState.RETIRED
    )


def test_candidate_retirement_also_requires_explicit_evidence() -> None:
    subject = candidate()
    with pytest.raises(RadarError, match="retirement requires"):
        TechnologyRadar((subject,)).decide(
            RadarDecision(subject.technology_id, RadarState.RETIRED, ()),
            1,
        )


def test_retired_state_is_terminal() -> None:
    subject = candidate()
    retirement = evidence(
        subject,
        "EVID.RETIRE",
        EvidenceKind.RETIREMENT,
        observed_tick=1,
    )
    radar = TechnologyRadar((subject,), (retirement,))
    radar.decide(
        RadarDecision(
            subject.technology_id,
            RadarState.RETIRED,
            (retirement.evidence_id,),
        ),
        1,
    )
    with pytest.raises(RadarError, match="transition"):
        radar.decide(
            RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
            2,
        )


def test_experiment_cannot_smuggle_architecture_adoption_authority() -> None:
    with pytest.raises(
        RadarError,
        match="only valid for adoption",
    ):
        RadarDecision(
            "TECH.1",
            RadarState.EXPERIMENT,
            (),
            "ADR.1",
        )


def test_evidence_set_identity_is_order_independent() -> None:
    subject = candidate()
    items = adoption_evidence(subject)
    assert technology_evidence_set_digest(items) == (
        technology_evidence_set_digest(reversed(items))
    )


def test_duplicate_evidence_in_evidence_set_rejected() -> None:
    subject = candidate()
    item = evidence(
        subject,
        "EVID.1",
        EvidenceKind.FUNCTIONAL,
    )
    with pytest.raises(RadarError, match="duplicate technology evidence"):
        technology_evidence_set_digest((item, item))


def test_duplicate_candidate_evidence_and_adr_ids_rejected() -> None:
    subject = candidate()
    with pytest.raises(RadarError, match="duplicate technology candidate"):
        TechnologyRadar((subject, subject))

    item = evidence(
        subject,
        "EVID.1",
        EvidenceKind.FUNCTIONAL,
    )
    with pytest.raises(RadarError, match="duplicate technology evidence"):
        TechnologyRadar((subject,), (item, item))

    items = adoption_evidence(subject)
    adr = architecture_decision(subject, items)
    with pytest.raises(RadarError, match="duplicate architecture decision"):
        TechnologyRadar((subject,), items, (adr, adr))


def test_candidate_budget_and_horizon_are_strictly_bounded() -> None:
    with pytest.raises(RadarError):
        TechnologyCandidate(
            "TECH.1",
            "x",
            "BASE.1",
            "OWNER.1",
            True,
            20,
            TechnologyExitCriteria(100, 5, 20),
        )
    with pytest.raises(RadarError, match="horizons must match"):
        TechnologyCandidate(
            "TECH.1",
            "x",
            "BASE.1",
            "OWNER.1",
            10,
            20,
            TechnologyExitCriteria(100, 5, 19),
        )
    with pytest.raises(RadarError, match="exceeds exit cost"):
        TechnologyCandidate(
            "TECH.1",
            "x",
            "BASE.1",
            "OWNER.1",
            101,
            20,
            TechnologyExitCriteria(100, 5, 20),
        )


def test_cost_and_risk_evidence_require_metrics() -> None:
    subject = candidate()
    with pytest.raises(RadarError, match="requires metric_value"):
        evidence(
            subject,
            "EVID.COST",
            EvidenceKind.COST,
        )
    with pytest.raises(RadarError, match="only valid"):
        evidence(
            subject,
            "EVID.F",
            EvidenceKind.FUNCTIONAL,
            metric_value=1,
        )


def test_snapshot_identity_changes_with_transition_history() -> None:
    subject = candidate()
    retirement = evidence(
        subject,
        "EVID.RETIRE",
        EvidenceKind.RETIREMENT,
        observed_tick=1,
    )
    radar = TechnologyRadar((subject,), (retirement,))
    before = radar.snapshot()
    radar.decide(
        RadarDecision(
            subject.technology_id,
            RadarState.RETIRED,
            (retirement.evidence_id,),
        ),
        1,
    )
    after = radar.snapshot()
    assert before.digest != after.digest
    assert before.registry_digest == after.registry_digest


def test_equivalent_transition_sequences_produce_same_snapshot_identity() -> None:
    subject = candidate()
    retirement = evidence(
        subject,
        "EVID.RETIRE",
        EvidenceKind.RETIREMENT,
        observed_tick=1,
    )
    first = TechnologyRadar((subject,), (retirement,))
    second = TechnologyRadar((subject,), (retirement,))
    decision = RadarDecision(
        subject.technology_id,
        RadarState.RETIRED,
        (retirement.evidence_id,),
    )
    first.decide(decision, 1)
    second.decide(decision, 1)
    assert first.snapshot().digest == second.snapshot().digest


def test_unknown_technology_and_boolean_tick_fail_closed() -> None:
    subject = candidate()
    radar = TechnologyRadar((subject,))
    with pytest.raises(RadarError, match="unknown technology"):
        radar.state("TECH.UNKNOWN")
    with pytest.raises(RadarError, match="current_tick"):
        radar.decide(
            RadarDecision(subject.technology_id, RadarState.EXPERIMENT, ()),
            True,
        )


def test_invalid_container_types_fail_closed() -> None:
    with pytest.raises(TypeError, match="TechnologyCandidate"):
        TechnologyRadar(("TECH.1",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TechnologyEvidence"):
        TechnologyRadar((candidate(),), ("EVID.1",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ArchitectureDecision"):
        TechnologyRadar(
            (candidate(),),
            (),
            ("ADR.1",),  # type: ignore[arg-type]
        )


def test_registry_materialization_stops_at_candidate_safety_bound() -> None:
    consumed = 0

    def candidates():
        nonlocal consumed
        while True:
            consumed += 1
            yield candidate(technology_id=f"TECH.{consumed}")

    with pytest.raises(RadarError, match="candidate count exceeds safety bound"):
        TechnologyRadar(candidates())
    assert consumed == 10_001


def test_evidence_set_materialization_stops_at_safety_bound() -> None:
    subject = candidate()
    item = evidence(subject, "EVID.BOUNDED", EvidenceKind.FUNCTIONAL)
    consumed = 0

    def items():
        nonlocal consumed
        while True:
            consumed += 1
            yield item

    with pytest.raises(RadarError, match="evidence set exceeds safety bound"):
        technology_evidence_set_digest(items())
    assert consumed == 50_001


def test_non_iterable_registry_inputs_fail_with_stable_type_errors() -> None:
    with pytest.raises(TypeError, match="candidates must be iterable"):
        TechnologyRadar(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="evidence must be iterable"):
        TechnologyRadar((), None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="architecture_decisions must be iterable"):
        TechnologyRadar((), (), None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="items must be iterable"):
        technology_evidence_set_digest(None)  # type: ignore[arg-type]
