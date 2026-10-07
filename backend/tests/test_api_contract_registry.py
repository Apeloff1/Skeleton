from __future__ import annotations

import pytest

from backend.core.api_contract_registry import (
    ApiContract,
    ApiContractError,
    CompatibilityClass,
    MigrationRule,
    evaluate_compatibility,
)


D1 = "1" * 64
D2 = "2" * 64
D3 = "3" * 64
D4 = "4" * 64


def _contract(**overrides) -> ApiContract:
    values = {
        "contract_id": "operations.stream",
        "version": 1,
        "method": "GET",
        "path": "/api/operations/{operation_id}/stream",
        "producer": "backend.routes.operation_stream",
        "consumers": ("web", "desktop"),
        "request_schema_digest": D1,
        "response_schema_digest": D2,
        "tenant_scoped": True,
        "idempotent": True,
    }
    values.update(overrides)
    return ApiContract(**values)


def _migration(**overrides) -> MigrationRule:
    values = {
        "contract_id": "operations.stream",
        "from_version": 1,
        "to_version": 2,
        "compatibility": CompatibilityClass.COMPATIBLE,
        "migration_id": "migration.operations.stream.v1-v2",
        "expires_at_epoch": 2_000_000_000,
    }
    values.update(overrides)
    return MigrationRule(**values)


def test_identical_registry_is_accepted_and_evidence_bearing() -> None:
    baseline = (_contract(),)
    decision = evaluate_compatibility(
        baseline,
        baseline,
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is True
    assert decision.unchanged == ("operations.stream",)
    assert decision.breaking == ()
    assert len(decision.accepted_evidence_ref().digest) == 64


def test_additive_contract_is_compatible() -> None:
    added = _contract(
        contract_id="operations.cancel",
        method="POST",
        path="/api/operations/{operation_id}/cancel",
        request_schema_digest=D3,
        response_schema_digest=D4,
    )
    decision = evaluate_compatibility(
        (_contract(),),
        (_contract(), added),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is True
    assert decision.additive == ("operations.cancel",)


def test_removed_contract_fails_closed() -> None:
    decision = evaluate_compatibility(
        (_contract(),),
        (_contract(contract_id="other", path="/api/other"),),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert any("removed" in item for item in decision.breaking)


def test_unversioned_schema_change_fails_closed() -> None:
    decision = evaluate_compatibility(
        (_contract(),),
        (_contract(response_schema_digest=D3),),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert decision.breaking == (
        "operations.stream:changed-without-version-advance",
    )


def test_invalid_contract_version_fails_during_construction() -> None:
    with pytest.raises(ApiContractError, match="version"):
        _contract(version=0)


def test_schema_change_requires_versioned_migration() -> None:
    candidate = _contract(version=2, response_schema_digest=D3)
    rejected = evaluate_compatibility(
        (_contract(),),
        (candidate,),
        observed_at_epoch=1_900_000_000,
    )
    assert rejected.accepted is False
    assert rejected.breaking == ("operations.stream:missing-migration-rule",)

    accepted = evaluate_compatibility(
        (_contract(),),
        (candidate,),
        migrations=(_migration(),),
        observed_at_epoch=1_900_000_000,
    )
    assert accepted.accepted is True


def test_operation_move_is_breaking_even_with_migration_rule() -> None:
    candidate = _contract(
        version=2,
        path="/api/v2/operations/{operation_id}/stream",
    )
    decision = evaluate_compatibility(
        (_contract(),),
        (candidate,),
        migrations=(_migration(),),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert decision.breaking == ("operations.stream:operation-moved",)


def test_expired_migration_window_fails_closed() -> None:
    candidate = _contract(version=2, request_schema_digest=D3)
    decision = evaluate_compatibility(
        (_contract(),),
        (candidate,),
        migrations=(_migration(expires_at_epoch=1_900_000_000),),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert decision.breaking == ("operations.stream:migration-window-expired",)


def test_rejected_decision_cannot_materialize_promotion_evidence() -> None:
    decision = evaluate_compatibility(
        (_contract(),),
        (),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    with pytest.raises(ApiContractError, match="cannot become promotion evidence"):
        decision.accepted_evidence_ref()


def test_duplicate_operation_or_contract_identity_rejected() -> None:
    with pytest.raises(ApiContractError, match="duplicate contract_id"):
        evaluate_compatibility(
            (_contract(), _contract()),
            (_contract(),),
            observed_at_epoch=1_900_000_000,
        )
    with pytest.raises(ApiContractError, match="duplicate operation"):
        evaluate_compatibility(
            (
                _contract(),
                _contract(contract_id="operations.stream.alias"),
            ),
            (_contract(),),
            observed_at_epoch=1_900_000_000,
        )

def test_empty_candidate_registry_reports_removal_and_cannot_emit_evidence() -> None:
    decision = evaluate_compatibility(
        (_contract(),),
        (),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert decision.breaking == ("operations.stream:removed",)
    with pytest.raises(ApiContractError, match="cannot become promotion evidence"):
        decision.accepted_evidence_ref()


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("tenant_scoped", False, "tenant-scope-semantics-changed"),
        ("idempotent", False, "idempotency-semantics-changed"),
        ("consumers", ("web",), "consumer-removed"),
    ),
)
def test_authority_and_consumer_semantics_are_absolute_breaks(
    field: str,
    value,
    reason: str,
) -> None:
    candidate = _contract(version=2, **{field: value})
    decision = evaluate_compatibility(
        (_contract(),),
        (candidate,),
        migrations=(_migration(),),
        observed_at_epoch=1_900_000_000,
    )
    assert decision.accepted is False
    assert decision.breaking == (f"operations.stream:{reason}",)
