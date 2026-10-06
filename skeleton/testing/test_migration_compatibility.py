from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.persistence.migration_compatibility import (
    MigrationCompatibilityError,
    MigrationPlan,
    RecordSchema,
    canonical_json_bytes,
    digest,
    reference_rehearsal,
    run_migration_rehearsal,
)


def _plan(*, semantic_drift: bool = False, rollback_drift: bool = False) -> MigrationPlan:
    source = RecordSchema(
        schema_id="fixture.record.v1",
        version=1,
        identity_fields=("record_id",),
        required_fields=("record_id", "value"),
    )
    target = RecordSchema(
        schema_id="fixture.record.v2",
        version=2,
        identity_fields=("record_id",),
        required_fields=("record_id", "value", "metadata"),
    )

    def forward(record):
        value = record["value"]
        if semantic_drift:
            value = {"rewritten": True}
        return {
            "schema_version": 2,
            "record_id": record["record_id"],
            "value": value,
            "metadata": {"source_schema": 1},
        }

    def rollback(record):
        value = record["value"]
        if rollback_drift:
            value = {"lost": True}
        return {
            "schema_version": 1,
            "record_id": record["record_id"],
            "value": value,
        }

    return MigrationPlan(
        migration_id="fixture.record.v1-v2",
        state_domain="fixture-domain",
        source=source,
        target=target,
        forward=forward,
        rollback=rollback,
        project=lambda record: {
            "record_id": record["record_id"],
            "value": record["value"],
        },
    )


def _records():
    return (
        {"schema_version": 1, "record_id": "a", "value": {"n": 1}},
        {"schema_version": 1, "record_id": "b", "value": {"n": 2}},
        {"schema_version": 1, "record_id": "c", "value": {"n": 3}},
        {"schema_version": 1, "record_id": "d", "value": {"n": 4}},
    )


def test_reference_rehearsal_is_fully_qualified_and_digest_bound() -> None:
    receipt = reference_rehearsal()

    assert receipt.qualified is True
    assert receipt.record_count == 3
    assert receipt.target_digest == receipt.replay_digest
    assert receipt.source_digest == receipt.rollback_digest
    assert receipt.source_digest == receipt.backup_digest
    assert receipt.source_digest == receipt.restore_digest
    assert receipt.source_projection_digest == receipt.target_projection_digest
    assert receipt.source_projection_digest == receipt.mixed_projection_digest
    assert len(receipt.receipt_digest) == 64
    assert receipt.as_dict()["qualified"] is True


def test_rehearsal_proves_forward_mixed_replay_rollback_and_restore() -> None:
    source = _records()
    before = deepcopy(source)

    receipt = run_migration_rehearsal(_plan(), source)

    assert receipt.qualified is True
    assert source == before
    assert receipt.record_count == 4
    assert receipt.target_digest == receipt.replay_digest
    assert receipt.source_projection_digest == receipt.mixed_projection_digest


def test_migration_replay_on_target_record_is_exact_noop() -> None:
    plan = _plan()
    migrated = plan.migrate(_records()[0])

    replayed = plan.migrate(migrated)

    assert replayed == migrated
    assert digest(replayed) == digest(migrated)


def test_mixed_version_projection_is_semantically_stable() -> None:
    plan = _plan()
    source = _records()
    target = [plan.migrate(record) for record in source]
    mixed = [target[0], source[1], target[2], source[3]]

    expected = [plan.semantic_projection(record) for record in source]
    actual = [plan.semantic_projection(record) for record in mixed]

    assert actual == expected


def test_semantic_drift_fails_before_qualification_receipt() -> None:
    with pytest.raises(
        MigrationCompatibilityError,
        match="changed semantic projection",
    ):
        run_migration_rehearsal(_plan(semantic_drift=True), _records())


def test_rollback_drift_fails_before_qualification_receipt() -> None:
    with pytest.raises(
        MigrationCompatibilityError,
        match="rollback did not restore the exact source snapshot",
    ):
        run_migration_rehearsal(_plan(rollback_drift=True), _records())


def test_identity_change_is_rejected_even_when_target_schema_is_valid() -> None:
    plan = _plan()

    def bad_forward(record):
        return {
            "schema_version": 2,
            "record_id": record["record_id"] + "-different",
            "value": record["value"],
            "metadata": {"source_schema": 1},
        }

    poisoned = MigrationPlan(
        migration_id="fixture.identity-poison.v1-v2",
        state_domain="fixture-domain",
        source=plan.source,
        target=plan.target,
        forward=bad_forward,
        rollback=plan.rollback,
        project=plan.project,
    )

    with pytest.raises(MigrationCompatibilityError, match="changed canonical record identity"):
        poisoned.migrate(_records()[0])


def test_duplicate_source_identity_fails_closed() -> None:
    duplicate = (
        _records()[0],
        {"schema_version": 1, "record_id": "a", "value": {"n": 99}},
    )
    with pytest.raises(MigrationCompatibilityError, match="duplicate identity"):
        run_migration_rehearsal(_plan(), duplicate)


def test_unknown_source_schema_fails_closed() -> None:
    plan = _plan()
    with pytest.raises(MigrationCompatibilityError, match="schema_version=1"):
        plan.migrate(
            {
                "schema_version": 99,
                "record_id": "a",
                "value": {"n": 1},
            }
        )


def test_nonfinite_and_nontext_json_are_rejected() -> None:
    with pytest.raises(MigrationCompatibilityError, match="non-finite"):
        canonical_json_bytes({"score": float("nan")})
    with pytest.raises(MigrationCompatibilityError, match="keys must be text"):
        canonical_json_bytes({1: "invalid"})


def test_schema_rejects_silent_unknown_field_loss() -> None:
    schema = RecordSchema(
        schema_id="fixture.strict.v1",
        version=1,
        identity_fields=("record_id",),
        required_fields=("record_id", "value"),
    )
    with pytest.raises(MigrationCompatibilityError, match="unknown fields"):
        schema.validate(
            {
                "schema_version": 1,
                "record_id": "a",
                "value": 1,
                "silent_legacy_field": "would-be-lost",
            }
        )


def test_source_and_target_schema_identity_must_align() -> None:
    source = RecordSchema(
        schema_id="fixture.source.v1",
        version=1,
        identity_fields=("record_id",),
        required_fields=("record_id", "value"),
    )
    target = RecordSchema(
        schema_id="fixture.target.v2",
        version=2,
        identity_fields=("other_id",),
        required_fields=("other_id", "value"),
    )
    plan = MigrationPlan(
        migration_id="fixture.bad-identity.v1-v2",
        state_domain="fixture-domain",
        source=source,
        target=target,
        forward=lambda record: {
            "schema_version": 2,
            "other_id": record["record_id"],
            "value": record["value"],
        },
        rollback=lambda record: {
            "schema_version": 1,
            "record_id": record["other_id"],
            "value": record["value"],
        },
        project=lambda record: {"value": record["value"]},
    )

    with pytest.raises(MigrationCompatibilityError, match="changed canonical record identity"):
        plan.migrate(
            {"schema_version": 1, "record_id": "a", "value": 1}
        )


def test_record_schema_configuration_is_fail_closed() -> None:
    with pytest.raises(MigrationCompatibilityError, match="identity fields"):
        RecordSchema(
            schema_id="fixture.invalid.v1",
            version=1,
            identity_fields=("record_id",),
            required_fields=("value",),
        )
    with pytest.raises(MigrationCompatibilityError, match="disjoint"):
        RecordSchema(
            schema_id="fixture.invalid.v1",
            version=1,
            identity_fields=("record_id",),
            required_fields=("record_id", "value"),
            optional_fields=("value",),
        )
