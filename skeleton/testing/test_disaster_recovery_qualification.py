from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.failure_knowledge import (
    FailureDisposition,
    FailureKnowledgeLedger,
    FailureKnowledgeQualificationDecision,
    FailureKnowledgeRecord,
    FailureSourceKind,
)
from skeleton.eval.regression_corpus import FailureClass
from skeleton.release.disaster_recovery import (
    DisasterRecoveryError,
    DisasterRecoveryDrillReceipt,
    DisasterScenario,
    IncidentCorrectiveAction,
    qualify_disaster_recovery,
)
from skeleton.release.restore import BackupRestoreQualificationDecision


COMMIT = "a" * 40
AUTHORITY = "b" * 64


def _restore(**overrides: object) -> BackupRestoreQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "source_commit": COMMIT,
        "migration_compatibility_digest": "1" * 64,
        "manifest_digest": "2" * 64,
        "authoritative_state_digest": AUTHORITY,
        "receipt_digests": ("3" * 64,),
    }
    values.update(overrides)
    return BackupRestoreQualificationDecision(**values)


def _record(
    index: int,
    *,
    incident_id: str,
) -> FailureKnowledgeRecord:
    return FailureKnowledgeRecord(
        record_id=f"incident-record-{index}",
        version=1,
        sequence=index,
        source_kind=FailureSourceKind.INCIDENT,
        source_ref=f"incident:{incident_id}",
        source_digest=f"{index:x}" * 64,
        failure_class=FailureClass.REASONING_ERROR,
        failure_fingerprint=f"{index + 3:x}" * 64,
        summary=f"Disaster recovery incident {incident_id}.",
        root_cause_digest=f"{index + 6:x}" * 64,
        risk_obligation_id=f"P1-RISK-DR-{index}",
        risk_obligation_digest=f"{index + 9:x}" * 64,
        disposition=FailureDisposition.REGRESSION_COVERED,
        evidence_refs=(
            EvidenceRef(
                source=f"failure://{incident_id}",
                digest=f"{index + 12:x}" * 64,
                category="failure_knowledge",
            ),
        ),
        regression_case_id=f"dr-regression-{index}",
        regression_case_version=1,
        regression_case_digest=f"{index + 1:x}" * 64,
    )


def _ledger() -> FailureKnowledgeLedger:
    return FailureKnowledgeLedger(
        ledger_id="p1-rel-05-incidents",
        version=1,
        records=(
            _record(1, incident_id="INC-1"),
            _record(2, incident_id="INC-2"),
            _record(3, incident_id="INC-3"),
        ),
    )


def _knowledge(
    ledger: FailureKnowledgeLedger,
    **overrides: object,
) -> FailureKnowledgeQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "ledger_digest": ledger.ledger_digest,
        "regression_corpus_digest": "d" * 64,
        "signal_digests": ("e" * 64,),
    }
    values.update(overrides)
    return FailureKnowledgeQualificationDecision(**values)


def _action(
    record: FailureKnowledgeRecord,
    *,
    action_id: str,
) -> IncidentCorrectiveAction:
    return IncidentCorrectiveAction(
        action_id=action_id,
        incident_id=record.source_ref.removeprefix("incident:"),
        incident_digest=record.source_digest,
        owner_id="owner:reliability",
        risk_obligation_id=record.risk_obligation_id,
        risk_obligation_digest=record.risk_obligation_digest,
        failure_knowledge_ledger_digest="0" * 64,
        failure_record_digest=record.record_digest,
        corrective_test_digest="f" * 64,
        evidence_refs=(
            EvidenceRef(
                source=f"incident://{action_id}",
                digest="1" * 64,
                category="incident_followup",
            ),
        ),
    )


def _fixture():
    restore = _restore()
    ledger = _ledger()
    knowledge = _knowledge(ledger)

    actions = []
    drills = []
    for index, scenario in enumerate(DisasterScenario, start=1):
        record = ledger.records[index - 1]
        action = replace(
            _action(record, action_id=f"action-{index}"),
            failure_knowledge_ledger_digest=ledger.ledger_digest,
        )
        actions.append(action)
        drills.append(
            DisasterRecoveryDrillReceipt(
                scenario=scenario,
                source_commit=COMMIT,
                backup_restore_qualification_digest=restore.decision_digest,
                authoritative_state_digest=AUTHORITY,
                pre_failure_state_digest=f"{index + 1:x}" * 64,
                recovered_state_digest=f"{index + 1:x}" * 64,
                rto_target_seconds=300.0,
                rto_observed_seconds=120.0,
                rpo_target_seconds=60.0,
                rpo_observed_seconds=20.0,
                incident_id=action.incident_id,
                incident_digest=action.incident_digest,
                corrective_action_ids=(action.action_id,),
                verifier_id=f"verifier:{scenario.value}",
                verifier_digest="2" * 64,
                test_manifest_digest="3" * 64,
                evidence_refs=(
                    EvidenceRef(
                        source=f"dr://{scenario.value}",
                        digest="4" * 64,
                        category="disaster_recovery",
                    ),
                ),
                passed=True,
                independent=True,
                production_mutation_count=0,
            )
        )
    return restore, ledger, knowledge, tuple(drills), tuple(actions)


def _qualify(
    *,
    restore=None,
    ledger=None,
    knowledge=None,
    drills=None,
    actions=None,
):
    d_restore, d_ledger, d_knowledge, d_drills, d_actions = _fixture()
    return qualify_disaster_recovery(
        backup_restore=d_restore if restore is None else restore,
        failure_knowledge=d_knowledge if knowledge is None else knowledge,
        failure_knowledge_ledger=d_ledger if ledger is None else ledger,
        drills=d_drills if drills is None else drills,
        corrective_actions=d_actions if actions is None else actions,
    )


def test_complete_dr_plan_qualifies() -> None:
    decision = _qualify()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.source_commit == COMMIT
    assert decision.authoritative_state_digest == AUTHORITY
    assert len(decision.drill_receipt_digests) == 3
    assert len(decision.corrective_action_digests) == 3

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "disaster_recovery_qualification"
    assert evidence.digest == decision.decision_digest


def test_upstream_restore_and_failure_knowledge_must_be_accepted() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()

    rejected_restore = replace(
        restore,
        accepted=False,
        reasons=("forced",),
    )
    decision = _qualify(
        restore=rejected_restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=actions,
    )
    assert "backup-restore-rejected" in decision.reasons

    rejected_knowledge = replace(
        knowledge,
        accepted=False,
        reasons=("forced",),
    )
    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=rejected_knowledge,
        drills=drills,
        actions=actions,
    )
    assert "failure-knowledge-rejected" in decision.reasons


def test_failure_knowledge_decision_must_bind_exact_ledger() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    knowledge = replace(knowledge, ledger_digest="0" * 64)

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=actions,
    )

    assert decision.accepted is False
    assert "failure-knowledge-ledger-digest-mismatch" in decision.reasons


@pytest.mark.parametrize("scenario", tuple(DisasterScenario))
def test_every_dr_scenario_is_required_once(
    scenario: DisasterScenario,
) -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    drills = tuple(item for item in drills if item.scenario is not scenario)

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=actions,
    )

    assert decision.accepted is False
    assert f"drill-cardinality:{scenario.value}" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("source_commit", "f" * 40, "source-commit-mismatch"),
        (
            "backup_restore_qualification_digest",
            "0" * 64,
            "backup-restore-digest-mismatch",
        ),
        (
            "authoritative_state_digest",
            "0" * 64,
            "authoritative-state-digest-mismatch",
        ),
    ),
)
def test_dr_receipt_binds_exact_restore_authority(
    field: str,
    value: str,
    suffix: str,
) -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(drills)
    rows[0] = replace(rows[0], **{field: value})

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=tuple(rows),
        actions=actions,
    )

    assert decision.accepted is False
    assert (
        f"authoritative_store_loss:{suffix}"
        in decision.reasons
    )


def test_semantic_recovery_must_restore_pre_failure_state() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(drills)
    rows[0] = replace(
        rows[0],
        recovered_state_digest="0" * 64,
    )

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=tuple(rows),
        actions=actions,
    )

    assert decision.accepted is False
    assert (
        "authoritative_store_loss:semantic-recovery-mismatch"
        in decision.reasons
    )


def test_rto_and_rpo_must_be_met() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(drills)
    rows[0] = replace(
        rows[0],
        rto_observed_seconds=301.0,
        rpo_observed_seconds=61.0,
    )

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=tuple(rows),
        actions=actions,
    )

    assert decision.accepted is False
    assert "authoritative_store_loss:rto-exceeded" in decision.reasons
    assert "authoritative_store_loss:rpo-exceeded" in decision.reasons


def test_missing_or_orphan_corrective_action_blocks() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    missing = actions[1:]
    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=missing,
    )
    assert decision.accepted is False
    assert any(
        "corrective-action-missing:action-1" in reason
        for reason in decision.reasons
    )

    orphan = replace(actions[0], action_id="orphan")
    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=(*actions, orphan),
    )
    assert "orphan-corrective-action:orphan" in decision.reasons


def test_corrective_action_must_point_to_exact_incident_record() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(actions)
    rows[0] = replace(
        rows[0],
        failure_record_digest="0" * 64,
    )

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=tuple(rows),
    )

    assert decision.accepted is False
    assert (
        "corrective-action-failure-record-missing:action-1"
        in decision.reasons
    )


def test_corrective_action_risk_identity_must_match_failure_record() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(actions)
    rows[0] = replace(
        rows[0],
        risk_obligation_digest="0" * 64,
    )

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=tuple(rows),
    )

    assert decision.accepted is False
    assert (
        "corrective-action-risk-identity-mismatch:action-1"
        in decision.reasons
    )


def test_corrective_action_incident_source_must_match() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(actions)
    rows[0] = replace(rows[0], incident_id="INC-other")

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=tuple(rows),
    )

    assert decision.accepted is False
    assert (
        "corrective-action-incident-source-mismatch:action-1"
        in decision.reasons
    )


def test_action_ledger_digest_must_match_learn06() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    rows = list(actions)
    rows[0] = replace(
        rows[0],
        failure_knowledge_ledger_digest="0" * 64,
    )

    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills,
        actions=tuple(rows),
    )

    assert decision.accepted is False
    assert (
        "corrective-action-failure-ledger-mismatch:action-1"
        in decision.reasons
    )


def test_corrective_action_requires_completed_independent_evidence() -> None:
    _, ledger, _, _, _ = _fixture()
    record = ledger.records[0]
    base = replace(
        _action(record, action_id="action"),
        failure_knowledge_ledger_digest=ledger.ledger_digest,
    )

    with pytest.raises(
        DisasterRecoveryError,
        match="must be completed",
    ):
        replace(base, completed=False)
    with pytest.raises(
        DisasterRecoveryError,
        match="independently verified",
    ):
        replace(base, independently_verified=False)
    with pytest.raises(
        DisasterRecoveryError,
        match="incident_followup evidence",
    ):
        replace(
            base,
            evidence_refs=(
                EvidenceRef(
                    source="incident://wrong",
                    digest="0" * 64,
                    category="wrong",
                ),
            ),
        )


def test_dr_receipt_requires_passing_independent_nonproduction_evidence() -> None:
    _, _, _, drills, _ = _fixture()
    base = drills[0]

    with pytest.raises(DisasterRecoveryError, match="must pass"):
        replace(base, passed=False)
    with pytest.raises(
        DisasterRecoveryError,
        match="independently verified",
    ):
        replace(base, independent=False)
    with pytest.raises(
        DisasterRecoveryError,
        match="cannot mutate production",
    ):
        replace(base, production_mutation_count=1)


def test_rejected_dr_cannot_materialize_promotion_evidence() -> None:
    restore, ledger, knowledge, drills, actions = _fixture()
    decision = _qualify(
        restore=restore,
        ledger=ledger,
        knowledge=knowledge,
        drills=drills[:-1],
        actions=actions,
    )

    assert decision.accepted is False
    with pytest.raises(
        DisasterRecoveryError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
