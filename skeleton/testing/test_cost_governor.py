from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorDenied,
    CostGovernorError,
    SafeCostFallback,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import TenantQuota
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


def _quota(
    *,
    max_cost_usd: float = 20.0,
    max_input_tokens: int = 20_000,
) -> TenantQuota:
    return TenantQuota(
        window_id="window-1",
        max_operations=100,
        max_input_tokens=max_input_tokens,
        max_output_tokens=20_000,
        max_cost_usd=max_cost_usd,
        max_tool_calls=100,
        max_artifact_bytes=1_000_000,
        max_storage_bytes=1_000_000,
        max_concurrent_operations=8,
    )


def _request(
    operation_id: str,
    *,
    capability: str = "model-premium",
    estimate: UsageEstimate | None = None,
    max_cost_usd: float = 10.0,
    max_queue_depth: int = 100,
) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability=capability,
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=max_cost_usd,
            max_wall_seconds=60.0,
            max_provider_attempts=4,
            max_tool_calls=20,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrency=8,
            max_queue_depth=max_queue_depth,
        ),
        estimate=estimate
        or UsageEstimate(
            input_tokens=1_000,
            output_tokens=200,
            cost_usd=2.0,
            wall_seconds=5.0,
            provider_attempts=1,
            tool_calls=1,
        ),
    )


def _fallback(
    *,
    reasons: tuple[str, ...] = ("cost_budget_exceeded",),
) -> SafeCostFallback:
    return SafeCostFallback(
        fallback_id="economy-v1",
        capability="model-economy",
        estimate=UsageEstimate(
            input_tokens=500,
            output_tokens=100,
            cost_usd=0.5,
            wall_seconds=3.0,
            provider_attempts=1,
            tool_calls=1,
        ),
        allowed_failure_reasons=reasons,
    )


def _evidence(label: str = "route") -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="cost_governor_test",
        ),
    )


def _governor(tmp_path, *, quota: TenantQuota | None = None) -> CostGovernor:
    return CostGovernor.durable(
        tmp_path / "quota.sqlite3",
        default_tenant_quota=quota or _quota(),
    )


def test_direct_reservation_uses_canonical_runtime_and_durable_ledger(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    governor = CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )

    receipt = governor.reserve(
        _request("op-direct"),
        now_wall=10.0,
    )

    assert receipt.fallback_used is False
    assert receipt.requested_capability == "model-premium"
    assert receipt.selected_capability == "model-premium"
    assert receipt.quota_reservation_digest is not None
    assert governor.active_reservations() == ("op-direct",)

    # Accounting state is durable even though active runtime leases are
    # intentionally process-local.
    restarted_ledger = SqliteTenantQuotaLedger(path)
    snapshot = restarted_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["cost_usd"] == pytest.approx(2.0)


def test_reservation_replay_is_idempotent_at_governor_boundary(tmp_path) -> None:
    governor = _governor(tmp_path)
    request = _request("op-replay")

    first = governor.reserve(request, now_wall=10.0)
    second = governor.reserve(request, now_wall=20.0)

    assert second == first
    assert governor.active_reservations() == ("op-replay",)


def test_same_operation_with_changed_requested_inputs_conflicts(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-conflict"), now_wall=10.0)

    with pytest.raises(
        CostGovernorError,
        match="different requested inputs",
    ):
        governor.reserve(
            _request(
                "op-conflict",
                estimate=UsageEstimate(
                    input_tokens=1_001,
                    output_tokens=200,
                    cost_usd=2.0,
                    wall_seconds=5.0,
                    provider_attempts=1,
                    tool_calls=1,
                ),
            ),
            now_wall=11.0,
        )


def test_declared_cheaper_fallback_handles_local_cost_denial(tmp_path) -> None:
    governor = _governor(tmp_path)
    request = _request(
        "op-local-fallback",
        estimate=UsageEstimate(
            input_tokens=1_000,
            output_tokens=200,
            cost_usd=2.0,
            wall_seconds=5.0,
            provider_attempts=1,
            tool_calls=1,
        ),
        max_cost_usd=1.0,
    )

    receipt = governor.reserve(
        request,
        fallback=_fallback(),
        now_wall=10.0,
    )

    assert receipt.fallback_used is True
    assert receipt.fallback_id == "economy-v1"
    assert receipt.fallback_reason == "cost_budget_exceeded"
    assert receipt.selected_capability == "model-economy"


def test_declared_cheaper_fallback_handles_durable_tenant_cost_denial(
    tmp_path,
) -> None:
    governor = _governor(
        tmp_path,
        quota=_quota(max_cost_usd=1.0),
    )
    request = _request(
        "op-quota-fallback",
        estimate=UsageEstimate(
            input_tokens=1_000,
            output_tokens=200,
            cost_usd=2.0,
            wall_seconds=5.0,
            provider_attempts=1,
            tool_calls=1,
        ),
    )
    fallback = _fallback(
        reasons=("tenant_quota_exceeded:",),
    )

    receipt = governor.reserve(
        request,
        fallback=fallback,
        now_wall=10.0,
    )

    assert receipt.fallback_used is True
    assert receipt.fallback_reason == "tenant_quota_exceeded:cost_usd"
    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["reserved"]["cost_usd"] == pytest.approx(0.5)


def test_fallback_cannot_bypass_queue_saturation(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.runtime.set_queue_depth(1)

    with pytest.raises(
        CostGovernorDenied,
        match="queue_saturated",
    ):
        governor.reserve(
            _request(
                "op-queue",
                max_queue_depth=1,
            ),
            fallback=_fallback(),
            now_wall=10.0,
        )

    assert governor.active_reservations() == ()


def test_fallback_contract_rejects_unsafe_failure_reason() -> None:
    with pytest.raises(
        CostGovernorError,
        match="unsafe fallback failure reason",
    ):
        SafeCostFallback(
            fallback_id="unsafe",
            capability="model-economy",
            estimate=UsageEstimate(cost_usd=0.1),
            allowed_failure_reasons=("queue_saturated",),
        )


def test_fallback_must_be_component_wise_cheaper(tmp_path) -> None:
    governor = _governor(tmp_path)
    request = _request(
        "op-not-cheaper",
        estimate=UsageEstimate(
            input_tokens=100,
            output_tokens=100,
            cost_usd=2.0,
            wall_seconds=2.0,
            provider_attempts=1,
        ),
        max_cost_usd=1.0,
    )
    fallback = SafeCostFallback(
        fallback_id="bad-fallback",
        capability="model-economy",
        estimate=UsageEstimate(
            input_tokens=101,
            output_tokens=50,
            cost_usd=0.5,
            wall_seconds=1.0,
            provider_attempts=1,
        ),
        allowed_failure_reasons=("cost_budget_exceeded",),
    )

    with pytest.raises(
        CostGovernorError,
        match="component-wise no greater and strictly cheaper",
    ):
        governor.reserve(
            request,
            fallback=fallback,
            now_wall=10.0,
        )


def test_incremental_charge_is_idempotent_and_durable(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-charge"), now_wall=10.0)
    delta = UsageEstimate(
        input_tokens=400,
        output_tokens=50,
        cost_usd=0.75,
        provider_attempts=1,
    )

    first = governor.charge(
        "op-charge",
        "provider-charge-1",
        "provider",
        delta,
        now_wall=10.5,
    )
    second = governor.charge(
        "op-charge",
        "provider-charge-1",
        "provider",
        delta,
        now_wall=11.0,
    )

    assert second == first
    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["usage_events"] == 1


def test_charge_replay_with_different_usage_conflicts(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-charge-conflict"), now_wall=10.0)
    governor.charge(
        "op-charge-conflict",
        "provider-charge-1",
        "provider",
        UsageEstimate(cost_usd=0.5),
        now_wall=10.5,
    )

    with pytest.raises(CostGovernorConflict):
        governor.charge(
            "op-charge-conflict",
            "provider-charge-1",
            "provider",
            UsageEstimate(cost_usd=0.6),
            now_wall=11.0,
        )


def test_unknown_usage_blocks_completion_until_conservatively_resolved(
    tmp_path,
) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-unknown"), now_wall=10.0)
    governor.mark_usage_unknown(
        "op-unknown",
        "provider-unknown-1",
        "provider",
        "provider omitted usage",
        now_wall=10.5,
    )

    with pytest.raises(
        CostGovernorError,
        match="actual_usage_unknown:provider",
    ):
        governor.complete(
            "op-unknown",
            UsageEstimate(),
            evidence_refs=_evidence("blocked"),
            now_wall=11.0,
        )

    assert governor.active_reservations() == ("op-unknown",)

    resolved = governor.resolve_unknown_usage(
        "op-unknown",
        "provider-unknown-1",
        UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.4,
            provider_attempts=1,
        ),
        now_wall=11.5,
    )
    assert resolved.resolved_unknown_usage is True

    decision = governor.complete(
        "op-unknown",
        UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.4,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("resolved"),
        now_wall=12.0,
    )

    assert decision.state == "completed"
    assert decision.accepted is True
    assert decision.reasons == ()
    assert governor.active_reservations() == ()


def test_empty_evidence_fails_before_consuming_runtime_lease(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-evidence"), now_wall=10.0)
    governor.charge(
        "op-evidence",
        "provider-1",
        "provider",
        UsageEstimate(cost_usd=0.4),
        now_wall=10.5,
    )

    with pytest.raises(
        CostGovernorError,
        match="evidence_refs must be non-empty",
    ):
        governor.complete(
            "op-evidence",
            UsageEstimate(cost_usd=0.4),
            evidence_refs=(),
            now_wall=11.0,
        )

    assert governor.active_reservations() == ("op-evidence",)
    assert governor.runtime.pressure.active_operations == 1


def test_successful_completion_is_qualified_against_durable_accounting(
    tmp_path,
) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-complete"), now_wall=10.0)
    governor.charge(
        "op-complete",
        "provider-1",
        "provider",
        UsageEstimate(
            input_tokens=500,
            output_tokens=100,
            cost_usd=1.0,
            provider_attempts=1,
        ),
        now_wall=10.5,
    )

    decision = governor.complete(
        "op-complete",
        UsageEstimate(
            input_tokens=500,
            output_tokens=100,
            cost_usd=1.0,
            wall_seconds=4.0,
            provider_attempts=1,
        ),
        evidence_refs=_evidence("complete"),
        now_wall=11.0,
    )

    assert decision.state == "completed"
    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.completion_digest is not None
    assert decision.accounting_decision_digest is not None
    assert decision.promotion_authority is False

    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["committed"]["cost_usd"] == pytest.approx(1.0)


def test_cost_overrun_completes_durably_but_is_not_accepted_evidence(
    tmp_path,
) -> None:
    governor = _governor(tmp_path)
    governor.reserve(
        _request(
            "op-overrun",
            estimate=UsageEstimate(
                input_tokens=100,
                output_tokens=50,
                cost_usd=1.0,
                wall_seconds=2.0,
                provider_attempts=1,
            ),
        ),
        now_wall=10.0,
    )
    governor.charge(
        "op-overrun",
        "provider-1",
        "provider",
        UsageEstimate(cost_usd=1.5),
        now_wall=10.5,
    )

    decision = governor.complete(
        "op-overrun",
        UsageEstimate(cost_usd=1.5),
        evidence_refs=_evidence("overrun"),
        now_wall=11.0,
    )

    assert decision.state == "completed"
    assert decision.accepted is False
    assert any("overrun" in reason for reason in decision.reasons)
    assert governor.active_reservations() == ()


def test_unspent_release_returns_reserved_capacity_without_committing_usage(
    tmp_path,
) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-release"), now_wall=10.0)

    decision = governor.release_unspent("op-release")

    assert decision.state == "released_unspent"
    assert decision.accepted is False
    assert decision.reasons == ("reservation-released-unspent",)
    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["operations"] == 0


def test_metered_usage_cannot_be_erased_by_unspent_release(tmp_path) -> None:
    governor = _governor(tmp_path)
    governor.reserve(_request("op-metered-release"), now_wall=10.0)
    governor.charge(
        "op-metered-release",
        "provider-1",
        "provider",
        UsageEstimate(cost_usd=0.5),
        now_wall=10.5,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="cannot release reservation after metered usage",
    ):
        governor.release_unspent("op-metered-release")

    assert governor.active_reservations() == ("op-metered-release",)


def test_governor_denial_does_not_leave_durable_reservation(tmp_path) -> None:
    governor = _governor(
        tmp_path,
        quota=_quota(max_input_tokens=10),
    )

    with pytest.raises(
        CostGovernorDenied,
        match="tenant_quota_exceeded:input_tokens",
    ):
        governor.reserve(
            _request(
                "op-denied",
                estimate=UsageEstimate(
                    input_tokens=11,
                    output_tokens=1,
                    cost_usd=0.1,
                    wall_seconds=1.0,
                    provider_attempts=1,
                ),
            ),
            now_wall=10.0,
        )

    snapshot = governor.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert governor.active_reservations() == ()
