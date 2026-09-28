from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.lifecycle import (
    InstallerLifecycleError,
    InstallerLifecycleReceipt,
    InstallerLifecycleScenario,
    qualify_installer_lifecycle,
)
from skeleton.release.qualification import ReleaseQualificationDecision


COMMIT = "a" * 40
INSTALLER = "b" * 64
TARGET = "2.0.0"
OWNERSHIP = "c" * 64
RETENTION = "d" * 64
TARGET_SNAPSHOT = "e" * 64
OLD_SNAPSHOT = "f" * 64
UNINSTALLED_SNAPSHOT = "1" * 64


def _release(**overrides: object) -> ReleaseQualificationDecision:
    values: dict[str, object] = {
        "accepted": True,
        "reasons": (),
        "source_commit": COMMIT,
        "release_evidence_digest": "2" * 64,
        "reproducibility_bundle_digest": "3" * 64,
        "reproducibility_evaluation_digest": "4" * 64,
        "dependency_evidence_digest": "5" * 64,
        "sbom_digest": "6" * 64,
        "provenance_digest": "7" * 64,
        "installer_metadata_digest": INSTALLER,
        "configuration_digest": "8" * 64,
        "lifecycle_receipt_digests": ("9" * 64,),
    }
    values.update(overrides)
    return ReleaseQualificationDecision(**values)


def _receipt(
    scenario: InstallerLifecycleScenario,
    release: ReleaseQualificationDecision,
    **overrides: object,
) -> InstallerLifecycleReceipt:
    before = OLD_SNAPSHOT
    after = TARGET_SNAPSHOT
    expected = TARGET_SNAPSHOT
    rollback = None
    retained = None
    interrupted = False
    recovered = False

    if scenario is InstallerLifecycleScenario.CLEAN_INSTALL:
        before = "0" * 64
    elif scenario is InstallerLifecycleScenario.INTERRUPTED_UPDATE:
        before = OLD_SNAPSHOT
        after = OLD_SNAPSHOT
        rollback = OLD_SNAPSHOT
        interrupted = True
        recovered = True
    elif scenario is InstallerLifecycleScenario.REPAIR:
        before = "a" * 64
    elif scenario is InstallerLifecycleScenario.REPAIR_REPEAT:
        before = TARGET_SNAPSHOT
        after = TARGET_SNAPSHOT
    elif scenario is InstallerLifecycleScenario.UNINSTALL:
        before = TARGET_SNAPSHOT
        after = UNINSTALLED_SNAPSHOT
        retained = "b" * 64

    values: dict[str, object] = {
        "scenario": scenario,
        "source_commit": release.source_commit,
        "release_qualification_digest": release.decision_digest,
        "installer_metadata_digest": INSTALLER,
        "target_version": TARGET,
        "before_snapshot_digest": before,
        "after_snapshot_digest": after,
        "expected_target_snapshot_digest": expected,
        "ownership_policy_digest": OWNERSHIP,
        "retention_policy_digest": RETENTION,
        "verifier_id": f"verifier:{scenario.value}",
        "verifier_digest": "c" * 64,
        "test_manifest_digest": "d" * 64,
        "evidence_refs": (
            EvidenceRef(
                source=f"lifecycle://{scenario.value}",
                digest="e" * 64,
                category=scenario.value,
            ),
        ),
        "rollback_snapshot_digest": rollback,
        "retained_user_data_digest": retained,
        "passed": True,
        "independent": True,
        "interrupted": interrupted,
        "recovered": recovered,
        "production_mutation_count": 0,
        "application_owned_residual_count": 0,
        "unowned_critical_count": 0,
    }
    values.update(overrides)
    return InstallerLifecycleReceipt(**values)


def _receipts(
    release: ReleaseQualificationDecision,
) -> tuple[InstallerLifecycleReceipt, ...]:
    return tuple(
        _receipt(scenario, release)
        for scenario in InstallerLifecycleScenario
    )


def _qualify(
    *,
    release: ReleaseQualificationDecision | None = None,
    receipts: tuple[InstallerLifecycleReceipt, ...] | None = None,
):
    release = release or _release()
    return qualify_installer_lifecycle(
        release_qualification=release,
        receipts=receipts or _receipts(release),
        installer_metadata_digest=INSTALLER,
        target_version=TARGET,
    )


def test_complete_lifecycle_qualifies() -> None:
    decision = _qualify()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.source_commit == COMMIT
    assert decision.installer_metadata_digest == INSTALLER
    assert decision.ownership_policy_digest == OWNERSHIP
    assert decision.retention_policy_digest == RETENTION
    assert len(decision.scenario_receipt_digests) == 6

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "installer_lifecycle_qualification"
    assert evidence.digest == decision.decision_digest



def test_rel02_installer_digest_must_match_rel01() -> None:
    release = _release(installer_metadata_digest="0" * 64)
    decision = _qualify(
        release=release,
        receipts=_receipts(release),
    )

    assert decision.accepted is False
    assert "release-installer-metadata-mismatch" in decision.reasons


def test_release_qualification_must_be_accepted() -> None:
    release = _release(
        accepted=False,
        reasons=("forced-release-rejection",),
    )
    decision = _qualify(
        release=release,
        receipts=_receipts(release),
    )

    assert decision.accepted is False
    assert "release-qualification-rejected" in decision.reasons


@pytest.mark.parametrize("scenario", tuple(InstallerLifecycleScenario))
def test_every_scenario_has_exact_cardinality(
    scenario: InstallerLifecycleScenario,
) -> None:
    release = _release()
    receipts = tuple(
        item
        for item in _receipts(release)
        if item.scenario is not scenario
    )

    decision = _qualify(release=release, receipts=receipts)

    assert decision.accepted is False
    assert f"scenario-cardinality:{scenario.value}" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("source_commit", "f" * 40, "source-commit-mismatch"),
        (
            "release_qualification_digest",
            "0" * 64,
            "release-qualification-mismatch",
        ),
        (
            "installer_metadata_digest",
            "0" * 64,
            "installer-metadata-mismatch",
        ),
        ("target_version", "9.9.9", "target-version-mismatch"),
    ),
)
def test_exact_release_and_installer_identity_is_bound(
    field: str,
    value: str,
    suffix: str,
) -> None:
    release = _release()
    receipts = list(_receipts(release))
    receipts[0] = replace(receipts[0], **{field: value})

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert f"clean_install:{suffix}" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("passed", False, "scenario-failed"),
        ("independent", False, "not-independent"),
        ("production_mutation_count", 1, "production-mutated"),
        ("unowned_critical_count", 1, "unowned-critical-state"),
    ),
)
def test_scenario_receipts_fail_closed(
    field: str,
    value: object,
    suffix: str,
) -> None:
    release = _release()
    receipts = list(_receipts(release))
    receipts[0] = replace(receipts[0], **{field: value})

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert f"clean_install:{suffix}" in decision.reasons


def test_clean_install_and_update_must_reach_target_snapshot() -> None:
    release = _release()
    receipts = list(_receipts(release))
    receipts[0] = replace(
        receipts[0],
        after_snapshot_digest="0" * 64,
    )
    update_index = list(InstallerLifecycleScenario).index(
        InstallerLifecycleScenario.UPDATE
    )
    receipts[update_index] = replace(
        receipts[update_index],
        after_snapshot_digest="1" * 64,
    )

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert "clean_install:target-snapshot-mismatch" in decision.reasons
    assert "update:target-snapshot-mismatch" in decision.reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        (
            {"interrupted": False},
            "interrupted_update:interruption-not-observed",
        ),
        (
            {"recovered": False},
            "interrupted_update:not-recovered",
        ),
        (
            {"rollback_snapshot_digest": None},
            "interrupted_update:rollback-snapshot-missing",
        ),
        (
            {
                "after_snapshot_digest": "0" * 64,
                "rollback_snapshot_digest": OLD_SNAPSHOT,
            },
            "interrupted_update:rollback-result-mismatch",
        ),
        (
            {
                "before_snapshot_digest": "0" * 64,
                "rollback_snapshot_digest": OLD_SNAPSHOT,
            },
            "interrupted_update:preupdate-state-not-restored",
        ),
    ),
)
def test_interrupted_update_requires_exact_rollback(
    changes: dict[str, object],
    reason: str,
) -> None:
    release = _release()
    receipts = list(_receipts(release))
    index = list(InstallerLifecycleScenario).index(
        InstallerLifecycleScenario.INTERRUPTED_UPDATE
    )
    receipts[index] = replace(receipts[index], **changes)

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_repair_must_restore_target_and_repeat_is_idempotent() -> None:
    release = _release()
    receipts = list(_receipts(release))
    repair_index = list(InstallerLifecycleScenario).index(
        InstallerLifecycleScenario.REPAIR
    )
    repeat_index = list(InstallerLifecycleScenario).index(
        InstallerLifecycleScenario.REPAIR_REPEAT
    )
    receipts[repair_index] = replace(
        receipts[repair_index],
        after_snapshot_digest="0" * 64,
    )
    receipts[repeat_index] = replace(
        receipts[repeat_index],
        before_snapshot_digest="1" * 64,
    )

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert "repair:target-snapshot-mismatch" in decision.reasons
    assert "repair_repeat:not-idempotent" in decision.reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        (
            {"application_owned_residual_count": 1},
            "uninstall:application-residue",
        ),
        (
            {"retained_user_data_digest": None},
            "uninstall:retention-evidence-missing",
        ),
        (
            {"after_snapshot_digest": TARGET_SNAPSHOT},
            "uninstall:application-state-still-installed",
        ),
    ),
)
def test_uninstall_residual_and_retention_contract(
    changes: dict[str, object],
    reason: str,
) -> None:
    release = _release()
    receipts = list(_receipts(release))
    index = list(InstallerLifecycleScenario).index(
        InstallerLifecycleScenario.UNINSTALL
    )
    receipts[index] = replace(receipts[index], **changes)

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_ownership_and_retention_policy_drift_blocks() -> None:
    release = _release()
    receipts = list(_receipts(release))
    receipts[0] = replace(
        receipts[0],
        ownership_policy_digest="0" * 64,
        retention_policy_digest="1" * 64,
    )

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert "ownership-policy-drift" in decision.reasons
    assert "retention-policy-drift" in decision.reasons


def test_receipt_requires_exact_scenario_evidence_category() -> None:
    release = _release()
    with pytest.raises(
        InstallerLifecycleError,
        match="exact scenario evidence category",
    ):
        _receipt(
            InstallerLifecycleScenario.REPAIR,
            release,
            evidence_refs=(
                EvidenceRef(
                    source="lifecycle://wrong",
                    digest="0" * 64,
                    category="clean_install",
                ),
            ),
        )


def test_rejected_lifecycle_cannot_materialize_promotion_evidence() -> None:
    release = _release()
    receipts = list(_receipts(release))
    receipts.pop()

    decision = _qualify(
        release=release,
        receipts=tuple(receipts),
    )

    assert decision.accepted is False
    with pytest.raises(
        InstallerLifecycleError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
