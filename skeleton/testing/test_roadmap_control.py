from __future__ import annotations

import hashlib

import pytest

from skeleton.automation import roadmap_control as compatibility
from skeleton.contracts import roadmap_control as canonical
from skeleton.contracts.roadmap_control import (
    RoadmapArchitectureDecision,
    RoadmapControl,
    RoadmapDependency,
    RoadmapError,
    RoadmapEvidence,
    RoadmapEvidenceKind,
    RoadmapItem,
    RoadmapRevision,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def item(
    item_id: str = "ROAD.1",
    *,
    work_package_id: str = "WP.1",
    build_node_id: str = "BUILD.1",
    risk_ids: tuple[str, ...] = ("RISK.1",),
    gate_ids: tuple[str, ...] = ("GATE.1",),
    top_level_scope: bool = False,
    architecture_decision_id: str | None = None,
) -> RoadmapItem:
    return RoadmapItem(
        item_id=item_id,
        work_package_id=work_package_id,
        build_node_id=build_node_id,
        risk_ids=risk_ids,
        acceptance_gate_ids=gate_ids,
        top_level_scope=top_level_scope,
        architecture_decision_id=architecture_decision_id,
    )


def evidence(
    subject: RoadmapItem,
    evidence_id: str,
    *,
    kind: RoadmapEvidenceKind = RoadmapEvidenceKind.BLOCKER,
    observed_tick: int = 2,
    active: bool = True,
    item_digest: str | None = None,
) -> RoadmapEvidence:
    return RoadmapEvidence(
        evidence_id=evidence_id,
        item_id=subject.item_id,
        item_digest=item_digest or subject.digest,
        kind=kind,
        artifact_digest=sha(evidence_id),
        observed_tick=observed_tick,
        active=active,
        producer_id="PRODUCER.ROADMAP",
    )


def architecture_decision(
    subject: RoadmapItem,
    *,
    decision_id: str | None = None,
    approved: bool = True,
    observed_tick: int = 2,
    item_digest: str | None = None,
) -> RoadmapArchitectureDecision:
    resolved = decision_id or subject.architecture_decision_id
    assert resolved is not None
    return RoadmapArchitectureDecision(
        decision_id=resolved,
        item_id=subject.item_id,
        item_digest=item_digest or subject.digest,
        evidence_digest=sha(f"{resolved}:evidence"),
        approved=approved,
        approver_id="APPROVER.ARCH",
        observed_tick=observed_tick,
    )


def revision(
    revision_id: str,
    parent_revision_id: str | None,
    item_ids: tuple[str, ...],
    *,
    assumption: str = "assumption-a",
    rationale: str = "bounded roadmap revision",
    evidence_ids: tuple[str, ...] = (),
    architecture_decision_ids: tuple[str, ...] = (),
    created_tick: int = 1,
) -> RoadmapRevision:
    return RoadmapRevision(
        revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        assumption_digest=sha(assumption),
        rationale=rationale,
        item_ids=item_ids,
        evidence_ids=evidence_ids,
        architecture_decision_ids=architecture_decision_ids,
        author_id="OWNER.ROADMAP",
        created_tick=created_tick,
    )


def test_automation_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_item_links_work_build_risk_and_acceptance_gate() -> None:
    subject = item()
    assert subject.work_package_id == "WP.1"
    assert subject.build_node_id == "BUILD.1"
    assert subject.risk_ids == ("RISK.1",)
    assert subject.acceptance_gate_ids == ("GATE.1",)


def test_breadth_freeze_item_requires_architecture_decision_identity() -> None:
    with pytest.raises(RoadmapError, match="architecture decision"):
        item(top_level_scope=True)

    subject = item(
        top_level_scope=True,
        architecture_decision_id="ADR.118",
    )
    assert subject.architecture_decision_id == "ADR.118"


def test_acceptance_gate_is_required() -> None:
    with pytest.raises(RoadmapError, match="non-empty"):
        item(gate_ids=())


def test_duplicate_risk_and_gate_links_fail_closed() -> None:
    with pytest.raises(RoadmapError, match="duplicate risk"):
        item(risk_ids=("RISK.1", "RISK.1"))
    with pytest.raises(RoadmapError, match="duplicate acceptance_gate"):
        item(gate_ids=("GATE.1", "GATE.1"))


def test_self_dependency_rejected() -> None:
    with pytest.raises(RoadmapError, match="self dependency"):
        RoadmapDependency("ROAD.1", "ROAD.1")


def test_unknown_dependency_endpoint_rejected() -> None:
    with pytest.raises(RoadmapError, match="unknown roadmap dependency"):
        RoadmapControl(
            (item(),),
            (RoadmapDependency("ROAD.1", "ROAD.9"),),
        )


def test_duplicate_dependency_rejected() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    edge = RoadmapDependency("ROAD.1", "ROAD.2")
    with pytest.raises(RoadmapError, match="duplicate roadmap dependency"):
        RoadmapControl((first, second), (edge, edge))


def test_dependency_cycle_rejected() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    with pytest.raises(RoadmapError, match="dependency cycle"):
        RoadmapControl(
            (first, second),
            (
                RoadmapDependency("ROAD.1", "ROAD.2"),
                RoadmapDependency("ROAD.2", "ROAD.1"),
            ),
        )


def test_topological_order_is_deterministic() -> None:
    one = item("ROAD.1")
    two = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    three = item(
        "ROAD.3",
        work_package_id="WP.3",
        build_node_id="BUILD.3",
        risk_ids=("RISK.3",),
        gate_ids=("GATE.3",),
    )
    control = RoadmapControl(
        (three, one, two),
        (
            RoadmapDependency("ROAD.1", "ROAD.3"),
            RoadmapDependency("ROAD.2", "ROAD.3"),
        ),
    )
    assert control.topological_order() == (
        "ROAD.1",
        "ROAD.2",
        "ROAD.3",
    )


def test_root_revision_can_activate_governed_items() -> None:
    subject = item()
    control = RoadmapControl((subject,))
    root = revision("REV.1", None, ("ROAD.1",), created_tick=1)
    assert control.add_revision(root) is root
    assert control.latest_revision is root


def test_only_first_revision_may_be_root() -> None:
    subject = item()
    control = RoadmapControl((subject,))
    control.add_revision(revision("REV.1", None, ("ROAD.1",)))
    with pytest.raises(RoadmapError, match="only first revision"):
        control.add_revision(revision("REV.2", None, ("ROAD.1",)))


def test_revision_requires_existing_parent() -> None:
    control = RoadmapControl((item(),))
    with pytest.raises(RoadmapError, match="unknown revision parent"):
        control.add_revision(
            revision("REV.2", "REV.1", ("ROAD.1",))
        )


def test_revision_cannot_reference_hidden_scope() -> None:
    control = RoadmapControl((item(),))
    with pytest.raises(RoadmapError, match="unknown item"):
        control.add_revision(
            revision("REV.1", None, ("ROAD.9",))
        )


def test_changed_revision_requires_replan_evidence() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    control = RoadmapControl((first, second))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(
        RoadmapError,
        match="requires blocker/assumption/risk evidence",
    ):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                created_tick=2,
            )
        )


def test_blocker_evidence_can_authorize_bounded_replan() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    blocker = evidence(
        second,
        "EVID.BLOCKER.2",
        kind=RoadmapEvidenceKind.BLOCKER,
        observed_tick=2,
    )
    control = RoadmapControl(
        (first, second),
        evidence=(blocker,),
    )
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    next_revision = revision(
        "REV.2",
        "REV.1",
        ("ROAD.1", "ROAD.2"),
        evidence_ids=(blocker.evidence_id,),
        created_tick=2,
    )
    assert control.add_revision(next_revision) is next_revision


def test_inactive_replan_evidence_rejected() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    blocker = evidence(
        second,
        "EVID.BLOCKER.2",
        active=False,
    )
    control = RoadmapControl((first, second), evidence=(blocker,))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="inactive"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(blocker.evidence_id,),
                created_tick=2,
            )
        )


def test_future_replan_evidence_rejected() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    blocker = evidence(
        second,
        "EVID.BLOCKER.2",
        observed_tick=5,
    )
    control = RoadmapControl((first, second), evidence=(blocker,))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="future roadmap evidence"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(blocker.evidence_id,),
                created_tick=2,
            )
        )


def test_replan_evidence_must_bind_changed_scope() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    unrelated = evidence(
        first,
        "EVID.BLOCKER.1",
    )
    control = RoadmapControl(
        (first, second),
        evidence=(unrelated,),
    )
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="does not bind changed"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(unrelated.evidence_id,),
                created_tick=2,
            )
        )


def test_evidence_must_bind_exact_item_revision() -> None:
    subject = item()
    stale = evidence(
        subject,
        "EVID.STALE",
        item_digest="0" * 64,
    )
    with pytest.raises(RoadmapError, match="evidence item digest mismatch"):
        RoadmapControl((subject,), evidence=(stale,))


def test_revision_cannot_drop_required_upstream_dependency() -> None:
    upstream = item("ROAD.1")
    downstream = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    blocker = evidence(
        upstream,
        "EVID.BLOCKER.1",
    )
    control = RoadmapControl(
        (upstream, downstream),
        (RoadmapDependency("ROAD.1", "ROAD.2"),),
        evidence=(blocker,),
    )
    control.add_revision(
        revision(
            "REV.1",
            None,
            ("ROAD.1", "ROAD.2"),
            created_tick=1,
        )
    )
    with pytest.raises(RoadmapError, match="required upstream dependency"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.2",),
                evidence_ids=(blocker.evidence_id,),
                created_tick=2,
            )
        )


def test_top_level_scope_addition_requires_exact_approved_decision() -> None:
    base = item("ROAD.1")
    addition = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
        top_level_scope=True,
        architecture_decision_id="ADR.118.2",
    )
    blocker = evidence(
        addition,
        "EVID.BLOCKER.2",
    )
    decision = architecture_decision(addition)
    control = RoadmapControl(
        (base, addition),
        evidence=(blocker,),
        architecture_decisions=(decision,),
    )
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )

    with pytest.raises(
        RoadmapError,
        match="missing exact architecture decision",
    ):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(blocker.evidence_id,),
                created_tick=2,
            )
        )

    accepted = revision(
        "REV.2",
        "REV.1",
        ("ROAD.1", "ROAD.2"),
        evidence_ids=(blocker.evidence_id,),
        architecture_decision_ids=(decision.decision_id,),
        created_tick=2,
    )
    assert control.add_revision(accepted) is accepted


def test_rejected_scope_decision_cannot_expand_breadth() -> None:
    base = item("ROAD.1")
    addition = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
        top_level_scope=True,
        architecture_decision_id="ADR.118.2",
    )
    blocker = evidence(addition, "EVID.BLOCKER.2")
    rejected = architecture_decision(addition, approved=False)
    control = RoadmapControl(
        (base, addition),
        evidence=(blocker,),
        architecture_decisions=(rejected,),
    )
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="rejected architecture decision"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(blocker.evidence_id,),
                architecture_decision_ids=(rejected.decision_id,),
                created_tick=2,
            )
        )


def test_future_scope_decision_cannot_expand_breadth() -> None:
    base = item("ROAD.1")
    addition = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
        top_level_scope=True,
        architecture_decision_id="ADR.118.2",
    )
    blocker = evidence(addition, "EVID.BLOCKER.2")
    future = architecture_decision(addition, observed_tick=5)
    control = RoadmapControl(
        (base, addition),
        evidence=(blocker,),
        architecture_decisions=(future,),
    )
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="future architecture decision"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=(blocker.evidence_id,),
                architecture_decision_ids=(future.decision_id,),
                created_tick=2,
            )
        )


def test_architecture_decision_must_bind_exact_item_revision() -> None:
    subject = item(
        top_level_scope=True,
        architecture_decision_id="ADR.118",
    )
    stale = architecture_decision(
        subject,
        item_digest="0" * 64,
    )
    with pytest.raises(
        RoadmapError,
        match="architecture decision item digest mismatch",
    ):
        RoadmapControl(
            (subject,),
            architecture_decisions=(stale,),
        )


def test_assumption_change_requires_replan_evidence_even_without_scope_change() -> None:
    subject = item()
    assumption_evidence = evidence(
        subject,
        "EVID.ASSUMPTION.1",
        kind=RoadmapEvidenceKind.ASSUMPTION,
    )
    control = RoadmapControl(
        (subject,),
        evidence=(assumption_evidence,),
    )
    control.add_revision(
        revision(
            "REV.1",
            None,
            ("ROAD.1",),
            assumption="a",
            created_tick=1,
        )
    )

    with pytest.raises(
        RoadmapError,
        match="requires blocker/assumption/risk evidence",
    ):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1",),
                assumption="b",
                created_tick=2,
            )
        )

    accepted = revision(
        "REV.2",
        "REV.1",
        ("ROAD.1",),
        assumption="b",
        evidence_ids=(assumption_evidence.evidence_id,),
        created_tick=2,
    )
    assert control.add_revision(accepted) is accepted


def test_revision_chronology_cannot_predate_parent() -> None:
    subject = item()
    control = RoadmapControl((subject,))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=5)
    )
    with pytest.raises(RoadmapError, match="chronology predates"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1",),
                created_tick=4,
            )
        )


def test_revision_diff_reports_scope_and_assumption_changes() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    blocker = evidence(second, "EVID.BLOCKER.2")
    control = RoadmapControl(
        (first, second),
        evidence=(blocker,),
    )
    root = revision(
        "REV.1",
        None,
        ("ROAD.1",),
        assumption="a",
        created_tick=1,
    )
    control.add_revision(root)
    next_revision = revision(
        "REV.2",
        "REV.1",
        ("ROAD.1", "ROAD.2"),
        assumption="b",
        evidence_ids=(blocker.evidence_id,),
        created_tick=2,
    )
    diff = control.diff(next_revision)
    assert diff.added_item_ids == ("ROAD.2",)
    assert diff.removed_item_ids == ()
    assert diff.assumption_changed is True
    assert diff.changed is True


def test_snapshot_identity_changes_with_revision_history() -> None:
    subject = item()
    control = RoadmapControl((subject,))
    before = control.snapshot()
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    after = control.snapshot()
    assert before.control_digest == after.control_digest
    assert before.digest != after.digest
    assert after.latest_revision_id == "REV.1"
    assert after.active_item_ids == ("ROAD.1",)


def test_control_identity_is_input_order_independent() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    edge = RoadmapDependency("ROAD.1", "ROAD.2")
    blocker = evidence(second, "EVID.BLOCKER.2")
    a = RoadmapControl(
        (first, second),
        (edge,),
        evidence=(blocker,),
    )
    b = RoadmapControl(
        (second, first),
        (edge,),
        evidence=(blocker,),
    )
    assert a.control_digest == b.control_digest


def test_duplicate_evidence_and_decision_identity_rejected() -> None:
    subject = item()
    proof = evidence(subject, "EVID.1")
    with pytest.raises(RoadmapError, match="duplicate roadmap evidence"):
        RoadmapControl(
            (subject,),
            evidence=(proof, proof),
        )

    scoped = item(
        top_level_scope=True,
        architecture_decision_id="ADR.118",
    )
    decision = architecture_decision(scoped)
    with pytest.raises(
        RoadmapError,
        match="duplicate roadmap architecture decision",
    ):
        RoadmapControl(
            (scoped,),
            architecture_decisions=(decision, decision),
        )


def test_revision_references_unknown_evidence_fail_closed() -> None:
    first = item("ROAD.1")
    second = item(
        "ROAD.2",
        work_package_id="WP.2",
        build_node_id="BUILD.2",
        risk_ids=("RISK.2",),
        gate_ids=("GATE.2",),
    )
    control = RoadmapControl((first, second))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    with pytest.raises(RoadmapError, match="unknown roadmap evidence"):
        control.add_revision(
            revision(
                "REV.2",
                "REV.1",
                ("ROAD.1", "ROAD.2"),
                evidence_ids=("EVID.MISSING",),
                created_tick=2,
            )
        )


def test_branching_revision_history_surfaces_multiple_tips() -> None:
    subject = item()
    assumption = evidence(
        subject,
        "EVID.ASSUMPTION.1",
        kind=RoadmapEvidenceKind.ASSUMPTION,
    )
    control = RoadmapControl((subject,), evidence=(assumption,))
    control.add_revision(
        revision("REV.1", None, ("ROAD.1",), created_tick=1)
    )
    control.add_revision(
        revision(
            "REV.2",
            "REV.1",
            ("ROAD.1",),
            assumption="b",
            evidence_ids=(assumption.evidence_id,),
            created_tick=2,
        )
    )
    control.add_revision(
        revision(
            "REV.3",
            "REV.1",
            ("ROAD.1",),
            assumption="c",
            evidence_ids=(assumption.evidence_id,),
            created_tick=2,
        )
    )
    with pytest.raises(RoadmapError, match="multiple tips"):
        _ = control.latest_revision


def test_tick_fields_reject_boolean_aliases() -> None:
    subject = item()
    with pytest.raises(RoadmapError, match="observed_tick"):
        evidence(
            subject,
            "EVID.1",
            observed_tick=True,  # type: ignore[arg-type]
        )
    with pytest.raises(RoadmapError, match="created_tick"):
        revision(
            "REV.1",
            None,
            ("ROAD.1",),
            created_tick=True,  # type: ignore[arg-type]
        )


def test_invalid_container_types_fail_closed() -> None:
    with pytest.raises(TypeError, match="RoadmapItem"):
        RoadmapControl(("ROAD.1",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RoadmapDependency"):
        RoadmapControl(
            (item(),),
            dependencies=("ROAD.1",),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="RoadmapEvidence"):
        RoadmapControl(
            (item(),),
            evidence=("EVID.1",),  # type: ignore[arg-type]
        )
