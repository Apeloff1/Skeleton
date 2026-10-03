from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.observability.cost_governor import (
    CostGovernor,
    CostGovernorConflict,
    CostGovernorError,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.quota import TenantQuota


def _quota() -> TenantQuota:
    return TenantQuota(
        window_id="recovery-window",
        max_operations=100,
        max_input_tokens=100_000,
        max_output_tokens=100_000,
        max_cost_usd=100.0,
        max_tool_calls=100,
        max_artifact_bytes=10_000_000,
        max_storage_bytes=10_000_000,
        max_concurrent_operations=8,
    )


def _request(operation_id: str) -> AdmissionRequest:
    return AdmissionRequest(
        operation_id=operation_id,
        tenant_id="tenant-a",
        capability="model-inference",
        budget=ResourceBudget(
            max_input_tokens=10_000,
            max_output_tokens=5_000,
            max_cost_usd=10.0,
            max_wall_seconds=60.0,
            max_provider_attempts=4,
            max_tool_calls=20,
            max_artifact_bytes=1_000_000,
            max_storage_bytes=1_000_000,
            max_concurrency=8,
            max_queue_depth=100,
        ),
        estimate=UsageEstimate(
            input_tokens=1_000,
            output_tokens=200,
            cost_usd=2.0,
            wall_seconds=5.0,
            provider_attempts=1,
        ),
    )


def _refs(label: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source=f"test:cost-recovery:{label}",
            digest=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            category="cost_governor_recovery",
        ),
    )


def _governor(path) -> CostGovernor:
    return CostGovernor.durable(
        path,
        default_tenant_quota=_quota(),
    )


def test_active_reservation_replays_across_process_restart(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    request = _request("op-replay-restart")
    first = _governor(path)

    initial = first.reserve(request, now_wall=10.0)
    first.charge(
        request.operation_id,
        "provider-1",
        "provider",
        UsageEstimate(
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.4,
            provider_attempts=1,
        ),
        now_wall=10.5,
    )

    restarted = _governor(path)
    replay = restarted.reserve(request, now_wall=20.0)

    assert replay == initial
    assert restarted.active_reservations() == (request.operation_id,)
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["usage_events"] == 1


def test_completed_decision_recovers_after_crash_between_reconcile_and_qualification(
    tmp_path,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-completion-crash"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)
    actual = UsageEstimate(
        input_tokens=500,
        output_tokens=100,
        cost_usd=1.0,
        wall_seconds=4.0,
        provider_attempts=1,
    )
    first.charge(
        operation,
        "provider-1",
        "provider",
        actual,
        now_wall=10.5,
    )

    # Crash injection: the spend ledger commits terminal accounting, but the
    # governor never reaches qualification/journal terminalization.
    completion = first.runtime.complete(
        operation,
        actual,
        now_wall=11.0,
    )
    assert completion.quota_completion is not None

    restarted = _governor(path)
    recovered = restarted.recover_completed(
        operation,
        evidence_refs=_refs("completion"),
    )

    assert recovered.state == "completed"
    assert recovered.accepted is True
    assert recovered.reasons == ()
    assert recovered.completion_digest is not None
    assert recovered.accounting_decision_digest is not None
    assert recovered.promotion_authority is False
    assert restarted.active_reservations() == ()

    # Exact terminal replay is stable without recomputing spend.
    replay = restarted.recover_completed(
        operation,
        evidence_refs=_refs("completion"),
    )
    assert replay == recovered
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "completions"
    ] == 1


def test_completed_recovery_rejects_different_evidence_replay(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-evidence-conflict"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    actual = UsageEstimate(cost_usd=0.5)
    first.charge(
        operation,
        "provider-1",
        "provider",
        actual,
        now_wall=10.5,
    )
    first.runtime.complete(operation, actual, now_wall=11.0)

    restarted = _governor(path)
    restarted.recover_completed(
        operation,
        evidence_refs=_refs("first"),
    )

    with pytest.raises(
        CostGovernorConflict,
        match="different evidence",
    ):
        restarted.recover_completed(
            operation,
            evidence_refs=_refs("second"),
        )


def test_terminal_completed_operation_cannot_be_reserved_again(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-terminal-replay"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    actual = UsageEstimate(cost_usd=0.5)
    first.charge(
        operation,
        "provider-1",
        "provider",
        actual,
        now_wall=10.5,
    )
    first.complete(
        operation,
        actual,
        evidence_refs=_refs("terminal"),
        now_wall=11.0,
    )

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="terminal cost journal",
    ):
        restarted.reserve(_request(operation), now_wall=20.0)


def test_release_recovers_if_process_dies_before_quota_release(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-release-before"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)

    def crash_before_release(_operation_id: str):
        raise SystemExit("simulated process loss before quota release")

    monkeypatch.setattr(first.runtime, "release", crash_before_release)

    with pytest.raises(SystemExit):
        first.release_unspent(operation)

    # The durable reservation is still present and the journal is pending.
    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 1

    restarted = _governor(path)
    recovered = restarted.recover_released(operation)

    assert recovered.state == "released_unspent"
    assert recovered.accepted is False
    assert recovered.reasons == ("reservation-released-unspent",)
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["committed"]["operations"] == 0


def test_release_recovers_if_process_dies_after_quota_release(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-release-after"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)

    assert first._journal is not None

    def crash_before_terminal(*_args, **_kwargs):
        raise SystemExit("simulated process loss after quota release")

    monkeypatch.setattr(
        first._journal,
        "record_terminal",
        crash_before_terminal,
    )

    with pytest.raises(SystemExit):
        first.release_unspent(operation)

    # The quota release committed, but the durable governor transition did not.
    assert first.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0

    restarted = _governor(path)
    recovered = restarted.recover_released(operation)

    assert recovered.state == "released_unspent"
    assert recovered.accepted is False
    assert restarted.runtime.quota_ledger.snapshot("tenant-a")[
        "active_reservations"
    ] == 0


def test_release_pending_blocks_new_operation_replay(tmp_path, monkeypatch) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-release-pending"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)

    def crash_before_release(_operation_id: str):
        raise SystemExit("simulated pending release")

    monkeypatch.setattr(first.runtime, "release", crash_before_release)
    with pytest.raises(SystemExit):
        first.release_unspent(operation)

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="release pending recovery",
    ):
        restarted.reserve(request, now_wall=20.0)


def test_recover_completed_requires_real_durable_completion(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-not-completed"
    governor = _governor(path)
    governor.reserve(_request(operation), now_wall=10.0)

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorError,
        match="no durable completed accounting",
    ):
        restarted.recover_completed(
            operation,
            evidence_refs=_refs("missing"),
        )


def test_release_recovery_rejects_completed_accounting(tmp_path) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-completed-not-release"
    first = _governor(path)
    first.reserve(_request(operation), now_wall=10.0)
    actual = UsageEstimate(cost_usd=0.5)
    first.charge(
        operation,
        "provider-1",
        "provider",
        actual,
        now_wall=10.5,
    )

    assert first._journal is not None
    active = first._active[operation]
    first._journal.mark_release_pending(operation, active.receipt)

    # Simulate an impossible-but-defensive race where accounting completes
    # while the governor journal says release is pending.
    first.runtime.complete(operation, actual, now_wall=11.0)

    restarted = _governor(path)
    with pytest.raises(
        CostGovernorConflict,
        match="completed accounting cannot be recovered",
    ):
        restarted.recover_released(operation)

    completed = restarted.recover_completed(
        operation,
        evidence_refs=_refs("completion-wins"),
    )
    assert completed.state == "completed"
    assert completed.accepted is True


def test_restart_journal_conflict_never_releases_preexisting_reservation(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "quota.sqlite3"
    operation = "op-replay-journal-conflict"
    request = _request(operation)
    first = _governor(path)
    first.reserve(request, now_wall=10.0)

    restarted = _governor(path)
    assert restarted._journal is not None

    def reject_replay(**_kwargs):
        raise CostGovernorConflict("simulated journal replay conflict")

    monkeypatch.setattr(
        restarted._journal,
        "record_active",
        reject_replay,
    )

    with pytest.raises(
        CostGovernorConflict,
        match="simulated journal replay conflict",
    ):
        restarted.reserve(request, now_wall=20.0)

    # The reservation predated this restart attempt, so a metadata disagreement
    # must not refund/delete it.
    snapshot = restarted.runtime.quota_ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["cost_usd"] == pytest.approx(2.0)
