from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission_runtime import AdmissionRuntimeConflict
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.shared_pressure import (
    SharedPressureConflict,
    SharedPressurePolicy,
    SqliteSharedPressureLedger,
)


_SCOPE = "cost-governor-shared-pressure"
_OWNER = "worker-a"


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="shared-pressure-reattach",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _request(
    operation_id: str,
    *,
    max_wall_seconds: float = 60.0,
    priority: int = 20,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=5.0,
            max_wall_seconds=max_wall_seconds,
            max_provider_attempts=4,
            max_tool_calls=20,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrency=4,
            max_queue_depth=100,
        ),
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.5,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        priority=priority,
    )


def _configure_pressure(path) -> SqliteSharedPressureLedger:
    ledger = SqliteSharedPressureLedger(path)
    ledger.configure(
        SharedPressurePolicy(
            scope=_SCOPE,
            max_concurrency=4,
            max_queue_depth=100,
            max_tenant_concurrency=4,
            max_tenant_queue_depth=100,
            soft_shed_fraction=1.0,
            protect_priority_at_or_below=10,
            default_lease_seconds=30.0,
        )
    )
    return ledger


def _governor(
    quota_path,
    pressure: SqliteSharedPressureLedger,
    *,
    owner: str = _OWNER,
) -> CostGovernor:
    return CostGovernor.durable(
        quota_path,
        default_tenant_quota=_quota(),
        shared_pressure_ledger=pressure,
        shared_pressure_scope=_SCOPE,
        shared_pressure_owner_id=owner,
    )


def _evidence(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:shared-pressure-reattach:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="shared_pressure_recovery",
        ),
    )


def test_live_shared_pressure_lease_reattaches_without_reacquire(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-live")
    first = _governor(quota_path, pressure)

    original = first.reserve(request, now_wall=10.0)
    shared = pressure.lease_for_operation(
        _SCOPE,
        request.operation_id,
        now=10.5,
    )
    assert shared is not None
    assert shared.owner_id == _OWNER

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(
        quota_path,
        restarted_pressure,
    )
    replay = restarted.reserve(request, now_wall=20.0)

    assert replay == original
    assert (
        restarted_pressure.lease_for_operation(
            _SCOPE,
            request.operation_id,
            now=20.5,
        )
        == shared
    )
    snapshot = restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    )
    assert snapshot.active == 1
    assert snapshot.tenant_active == 1


def test_completed_reattached_operation_releases_shared_capacity(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-complete")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    restarted.reserve(request, now_wall=20.0)

    decision = restarted.complete(
        request.operation_id,
        UsageEstimate(
            input_tokens=120,
            output_tokens=25,
            cost_usd=0.7,
            wall_seconds=3.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("complete"),
        now_wall=21.0,
    )

    assert decision.state == "completed"
    assert (
        restarted_pressure.lease_for_operation(
            _SCOPE,
            request.operation_id,
            now=21.5,
        )
        is None
    )
    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=21.5,
    ).active == 0


def test_shared_pressure_owner_drift_fails_closed_without_mutation(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-owner-drift")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
        owner="worker-b",
    )
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease identity does not match runtime",
    ):
        restarted.reserve(request, now_wall=20.0)

    quota_snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert quota_snapshot["active_reservations"] == 1
    assert SqliteSharedPressureLedger(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1


def test_expired_shared_pressure_lease_is_not_reacquired(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request(
        "op-expired-shared",
        max_wall_seconds=5.0,
    )
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease is no longer active",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 0


def test_deleted_shared_pressure_lease_is_not_reacquired(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-deleted-shared")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    lease = pressure.lease_for_operation(
        _SCOPE,
        request.operation_id,
        now=10.5,
    )
    assert lease is not None
    pressure.release(lease.lease_id, lease.owner_id)

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
    )
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease is no longer active",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_legacy_missing_shared_pressure_metadata_fails_closed(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-legacy-shared")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(quota_path) as conn:
        row = conn.execute(
            """
            SELECT runtime_lease_json
            FROM cost_governor_journal
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload.pop("shared_pressure_lease", None)
        conn.execute(
            """
            UPDATE cost_governor_journal
            SET runtime_lease_json = ?
            WHERE operation_id = ?
            """,
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                request.operation_id,
            ),
        )

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
    )
    with pytest.raises(
        CostGovernorError,
        match="shared_pressure_reattach_requires_durable_lease_metadata",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1
    assert SqliteSharedPressureLedger(pressure_path).snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1


def test_tampered_shared_pressure_owner_is_rejected(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-tampered-shared-owner")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(quota_path) as conn:
        row = conn.execute(
            """
            SELECT runtime_lease_json
            FROM cost_governor_journal
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["shared_pressure_lease"]["owner_id"] = "worker-b"
        conn.execute(
            """
            UPDATE cost_governor_journal
            SET runtime_lease_json = ?
            WHERE operation_id = ?
            """,
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                request.operation_id,
            ),
        )

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
    )
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure lease identity does not match runtime",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_effect_authority_expiry_fences_new_effects_but_not_accounting(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request(
        "op-effect-expiry",
        max_wall_seconds=5.0,
    )
    governor = _governor(quota_path, pressure)
    governor.reserve(request, now_wall=10.0)

    live = governor.runtime.require_effect_authority(
        request.operation_id,
        now_wall=14.999,
    )
    assert live.operation_id == request.operation_id

    with pytest.raises(
        AdmissionRuntimeConflict,
        match="effect authority expired",
    ):
        governor.runtime.require_effect_authority(
            request.operation_id,
            now_wall=15.0,
        )

    # Expiry fences future effects, but terminal accounting must remain
    # available so known usage cannot become an unrecoverable reservation.
    completed = governor.complete(
        request.operation_id,
        UsageEstimate(
            input_tokens=120,
            output_tokens=25,
            cost_usd=0.7,
            wall_seconds=5.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("effect-expiry-accounting"),
        now_wall=16.0,
    )
    assert completed.state == "completed"
    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1


def test_effect_authority_rejects_replacement_lease_split_brain(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request(
        "op-effect-replaced",
        max_wall_seconds=5.0,
    )
    governor = _governor(quota_path, pressure)
    governor.reserve(request, now_wall=10.0)

    replacement = pressure.acquire(
        _SCOPE,
        request.tenant_id,
        request.operation_id,
        "worker-b",
        priority=request.priority,
        lease_seconds=30.0,
        now=16.0,
    )
    assert replacement.owner_id == "worker-b"

    with pytest.raises(
        AdmissionRuntimeConflict,
        match="effect authority does not match active lease",
    ):
        governor.runtime.require_effect_authority(
            request.operation_id,
            now_wall=16.5,
        )


def test_expired_shared_pressure_lease_cannot_be_renewed(
    tmp_path,
) -> None:
    pressure = _configure_pressure(tmp_path / "pressure.sqlite3")
    lease = pressure.acquire(
        _SCOPE,
        "tenant-a",
        "op-renew-expired",
        _OWNER,
        priority=20,
        lease_seconds=5.0,
        now=10.0,
    )

    with pytest.raises(
        SharedPressureConflict,
        match="pressure lease expired",
    ):
        pressure.renew(
            lease.lease_id,
            lease.owner_id,
            lease_seconds=30.0,
            now=15.0,
        )

    # The failed renewal cannot move the durable expiry boundary.
    assert (
        pressure.lease_for_operation(
            _SCOPE,
            lease.operation_id,
            now=15.0,
        )
        is None
    )
    assert pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=15.0,
    ).active == 0


def test_live_shared_pressure_lease_can_renew_before_expiry(
    tmp_path,
) -> None:
    pressure = _configure_pressure(tmp_path / "pressure.sqlite3")
    lease = pressure.acquire(
        _SCOPE,
        "tenant-a",
        "op-renew-live",
        _OWNER,
        priority=20,
        lease_seconds=5.0,
        now=10.0,
    )

    renewed = pressure.renew(
        lease.lease_id,
        lease.owner_id,
        lease_seconds=30.0,
        now=14.999,
    )

    assert renewed.lease_id == lease.lease_id
    assert renewed.acquired_at == lease.acquired_at
    assert renewed.expires_at == pytest.approx(44.999)
    assert (
        pressure.lease_for_operation(
            _SCOPE,
            lease.operation_id,
            now=15.0,
        )
        == renewed
    )


def test_live_shared_pressure_lookup_reaps_expired_lease(tmp_path) -> None:
    pressure = _configure_pressure(tmp_path / "pressure.sqlite3")
    lease = pressure.acquire(
        _SCOPE,
        "tenant-a",
        "op-lookup-expiry",
        _OWNER,
        priority=20,
        lease_seconds=5.0,
        now=10.0,
    )
    assert pressure.lease_for_operation(
        _SCOPE,
        lease.operation_id,
        now=14.0,
    ) == lease
    assert (
        pressure.lease_for_operation(
            _SCOPE,
            lease.operation_id,
            now=16.0,
        )
        is None
    )
    assert pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=16.0,
    ).active == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("priority", "20"),
        ("acquired_at", "10.0"),
        ("expires_at", True),
    ],
)
def test_coercive_shared_pressure_journal_fields_are_rejected(
    tmp_path,
    field,
    value,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-coercive-" + field)
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    with sqlite3.connect(quota_path) as conn:
        row = conn.execute(
            """
            SELECT runtime_lease_json
            FROM cost_governor_journal
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["shared_pressure_lease"][field] = value
        conn.execute(
            """
            UPDATE cost_governor_journal
            SET runtime_lease_json = ?
            WHERE operation_id = ?
            """,
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                request.operation_id,
            ),
        )

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
    )
    with pytest.raises(
        CostGovernorError,
        match="shared pressure lease journal payload is invalid",
    ):
        restarted.reserve(request, now_wall=20.0)

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_failed_completion_preserves_shared_pressure_authority(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-failed-complete")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    restarted.reserve(request, now_wall=20.0)
    restarted.mark_usage_unknown(
        request.operation_id,
        "provider-unknown-shared",
        "provider",
        "provider usage unresolved",
        now_wall=20.5,
    )

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        restarted.complete(
            request.operation_id,
            UsageEstimate(
                input_tokens=120,
                output_tokens=25,
                cost_usd=0.7,
                wall_seconds=3.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("failed-complete"),
            now_wall=21.0,
        )

    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=21.5,
    ).active == 1
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1


def test_failed_unspent_release_preserves_shared_pressure_authority(
    tmp_path,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-failed-release")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    restarted.reserve(request, now_wall=20.0)
    restarted.charge(
        request.operation_id,
        "provider-metered-shared",
        "provider",
        UsageEstimate(
            input_tokens=20,
            output_tokens=5,
            cost_usd=0.1,
        ),
        now_wall=20.5,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="cannot release reservation after metered usage",
    ):
        restarted.release_unspent(request.operation_id)

    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=21.0,
    ).active == 1
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["usage_events"] == 1


def test_recover_completed_settles_live_shared_pressure_after_crash(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-recover-completed")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    def crash_before_pressure_release(_lease) -> None:
        raise SystemExit("simulated crash after quota completion")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )

    with pytest.raises(SystemExit):
        first.complete(
            request.operation_id,
            UsageEstimate(
                input_tokens=120,
                output_tokens=25,
                cost_usd=0.7,
                wall_seconds=3.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("recover-completed"),
            now_wall=20.0,
        )

    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "completions"
    ] == 1
    assert pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 1

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    recovered = restarted.recover_completed(
        request.operation_id,
        evidence_refs=_evidence("recover-completed"),
        now_wall=21.0,
    )

    assert recovered.state == "completed"
    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=21.5,
    ).active == 0


def test_recover_released_settles_live_shared_pressure_after_crash(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-recover-release")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    def crash_before_pressure_release(_lease) -> None:
        raise SystemExit("simulated crash after quota release")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )

    with pytest.raises(SystemExit):
        first.release_unspent(request.operation_id)

    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0
    assert pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.0,
    ).active == 1

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    recovered = restarted.recover_released(
        request.operation_id,
        now_wall=20.5,
    )

    assert recovered.state == "released_unspent"
    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=21.0,
    ).active == 0


def test_terminal_recovery_accepts_already_expired_pressure_as_settled(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request(
        "op-shared-recover-expired",
        max_wall_seconds=5.0,
    )
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    def crash_before_pressure_release(_lease) -> None:
        raise SystemExit("simulated crash before pressure cleanup")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )
    with pytest.raises(SystemExit):
        first.complete(
            request.operation_id,
            UsageEstimate(
                input_tokens=120,
                output_tokens=25,
                cost_usd=0.7,
                wall_seconds=3.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("recover-expired"),
            now_wall=12.0,
        )

    restarted_pressure = SqliteSharedPressureLedger(pressure_path)
    restarted = _governor(quota_path, restarted_pressure)
    recovered = restarted.recover_completed(
        request.operation_id,
        evidence_refs=_evidence("recover-expired"),
        now_wall=20.0,
    )

    assert recovered.state == "completed"
    assert restarted_pressure.snapshot(
        _SCOPE,
        tenant_id="tenant-a",
        now=20.5,
    ).active == 0


def test_terminal_recovery_rejects_tampered_live_pressure_ledger(
    tmp_path,
    monkeypatch,
) -> None:
    quota_path = tmp_path / "quota.sqlite3"
    pressure_path = tmp_path / "pressure.sqlite3"
    pressure = _configure_pressure(pressure_path)
    request = _request("op-shared-recover-tampered")
    first = _governor(quota_path, pressure)
    first.reserve(request, now_wall=10.0)

    def crash_before_pressure_release(_lease) -> None:
        raise SystemExit("simulated crash after quota completion")

    monkeypatch.setattr(
        first.runtime,
        "_release_shared_pressure",
        crash_before_pressure_release,
    )
    with pytest.raises(SystemExit):
        first.complete(
            request.operation_id,
            UsageEstimate(
                input_tokens=120,
                output_tokens=25,
                cost_usd=0.7,
                wall_seconds=3.0,
                provider_attempts=1,
            ),
            evidence_refs=_evidence("recover-tampered"),
            now_wall=20.0,
        )

    with sqlite3.connect(pressure_path) as conn:
        conn.execute(
            """
            UPDATE shared_pressure_lease
            SET expires_at = expires_at + 1
            WHERE operation_id = ?
            """,
            (request.operation_id,),
        )

    restarted = _governor(
        quota_path,
        SqliteSharedPressureLedger(pressure_path),
    )
    with pytest.raises(
        CostGovernorConflict,
        match="shared pressure recovery lease does not match durable ledger",
    ):
        restarted.recover_completed(
            request.operation_id,
            evidence_refs=_evidence("recover-tampered"),
            now_wall=21.0,
        )

    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "completions"
    ] == 1
