"""Per-token CPU pressure guard regressions with deterministic OS probe doubles."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
from skeleton.ai.model_runtime import native_token_pressure as pressure_module
from skeleton.ai.model_runtime.native_token_pressure import (
    NativePressureInterrupted, NativeTokenPressureGuard,
)

P = DispatchPermit(
    lease_id="b" * 64, request_id="r", generation=1,
    checkpoint_digest="c" * 64, tokens=2, bytes_reserved=32,
)


def budget(*, tokens=2, slots=1, ram=4096, pressure=0):
    return MeasuredStreamBudget(
        available_ram_bytes=ram, reserved_ram_bytes=0,
        token_budget=tokens, stream_slots=slots,
        pressure_ppm=pressure, thermal_hold=False, measurement="os_probe",
    )


def canonical_evidence():
    """Complete canonical OS evidence fixture; never simulated hardware authority."""
    return {
        "schema": "skeleton.ai.live-stream-pressure.v1",
        "measurement": "os_probe",
        "gpu_device_qualified": False,
        "physical_memory_reserved": False,
        "cross_process_admission_guaranteed": False,
        "auxiliary_telemetry_incomplete": True,
        "thermal_trip_measured": True,
        "cgroup_swap_spill_allowed": True,
        "cgroup_swap_limit_measured": True,
        "cgroup_memory_limit_measured": True,
        "holds": {
            "thermal": False, "cgroup_high": False, "cgroup_oom": False,
            "cgroup_memory": False, "cgroup_swap_spill": False,
            "io": False, "cpu_throttle": False, "swap_churn": False,
            "reclaim": False, "disk_reserve": False,
        },
    }


def probe(monkeypatch, readings, *, evidence=None):
    iterator = iter(readings)

    def sample(self, *, token_budget, storage_path):
        item = next(iterator)
        if isinstance(item, BaseException):
            raise item
        return item, canonical_evidence() if evidence is None else evidence
    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)


def test_pressure_healthy_callbacks_preserve_single_flight(monkeypatch):
    probe(monkeypatch, [budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    interrupt()
    assert guard.status().samples == 2
    assert not guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)
    guard.finish(success=True)
    assert not guard.status().stopped


def test_pressure_rise_aborts_and_remains_stopped(monkeypatch):
    probe(monkeypatch, [budget(), budget(slots=0)])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="pressure hold"):
        interrupt()
    assert guard.status().stopped
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_missing_telemetry_fails_closed(monkeypatch):
    probe(monkeypatch, [OSError("unavailable")])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="unavailable"):
        guard.start(P)()
    assert guard.status().stopped


def test_probe_count_is_hard_bound(monkeypatch):
    probe(monkeypatch, [budget()])
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_probes=1,
    )
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="probe budget"):
        interrupt()
    assert guard.status().samples == 1


def test_unqualified_permit_denied_before_sampling():
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="CPU-only"):
        guard.start(replace(P, device_qualified=True))


@pytest.mark.parametrize("limit", [0, True, 4097])
def test_probe_budget_validation(limit):
    with pytest.raises(ValueError, match="probe count"):
        NativeTokenPressureGuard(
            LiveStreamBudgetSampler(), storage_path=".", max_probes=limit,
        )


def test_unobserved_success_cannot_reset_guard_to_available():
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    guard.start(P)
    with pytest.raises(NativePressureInterrupted, match="unverified"):
        guard.finish(success=True)
    assert guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_one_callback_is_not_proof_of_postflight_and_model_probes(monkeypatch):
    probe(monkeypatch, [budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    interrupt = guard.start(P)
    interrupt()
    with pytest.raises(NativePressureInterrupted, match="unverified"):
        guard.finish(success=True)
    assert guard.status().stopped


def test_active_status_cannot_report_healthy_after_deadline(monkeypatch):
    values = iter((100, 100 + 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(values))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    guard.start(P)
    with pytest.raises(NativePressureInterrupted, match="deadline exceeded"):
        guard.status()
    assert guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_active_status_rejects_clock_regression_without_sampling(monkeypatch):
    values = iter((100, 99))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(values))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".",
    )
    guard.start(P)
    with pytest.raises(NativePressureInterrupted, match="clock regressed"):
        guard.status()
    assert guard.status().stopped


def test_monotonic_deadline_interrupts_before_another_token(monkeypatch):
    probe(monkeypatch, [budget()])
    clock = iter((0, 100, 200, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    callback = guard.start(P)
    callback()
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        callback()
    assert guard.status().samples == 1
    assert guard.status().stopped
    guard.finish(success=False)


def test_probe_time_counts_toward_execution_deadline(monkeypatch):
    probe(monkeypatch, [budget()])
    clock = iter((0, 10, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        guard.start(P)()
    assert guard.status().samples == 1
    assert guard.status().stopped


def test_clock_regression_quarantines_active_native_lease(monkeypatch):
    clock = iter((1000, 999))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="regressed"):
        guard.start(P)()
    assert guard.status().stopped


def test_deadline_expiry_at_finish_cannot_certify_success(monkeypatch):
    probe(monkeypatch, [budget(), budget()])
    clock = iter((0, 10, 20, 30, 40, 1_000_001))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(clock))
    guard = NativeTokenPressureGuard(
        LiveStreamBudgetSampler(), storage_path=".", max_duration_ns=1_000_000,
    )
    callback = guard.start(P)
    callback()
    callback()
    with pytest.raises(NativePressureInterrupted, match="deadline"):
        guard.finish(success=True)
    assert guard.status().samples == 2
    assert guard.status().stopped
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(P)


def test_monotonic_clock_failure_at_start_is_fail_closed(monkeypatch):
    def broken_clock():
        raise OSError("clock failed")
    monkeypatch.setattr(pressure_module, "monotonic_ns", broken_clock)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="unavailable"):
        guard.start(P)
    assert guard.status().stopped


@pytest.mark.parametrize("duration", [0, True, 999_999, 86_400_000_000_001])
def test_native_execution_duration_must_be_bounded(duration):
    with pytest.raises(ValueError, match="duration"):
        NativeTokenPressureGuard(
            LiveStreamBudgetSampler(), storage_path=".",
            max_duration_ns=duration,
        )


def test_native_pressure_guard_burns_successful_lease_and_fences_old_callback(monkeypatch):
    probe(monkeypatch, [budget(), budget(), budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    old_callback = guard.start(P)
    old_callback()
    old_callback()
    guard.finish(success=True)
    with pytest.raises(NativePressureInterrupted, match="replay"):
        guard.start(P)
    assert guard.status().stopped


def test_native_pressure_old_callback_cannot_sample_new_lease(monkeypatch):
    probe(monkeypatch, [budget(), budget(), budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    old_callback = guard.start(P)
    old_callback()
    old_callback()
    guard.finish(success=True)
    new_permit = replace(P, lease_id="d" * 64, request_id="next")
    new_callback = guard.start(new_permit)
    with pytest.raises(NativePressureInterrupted, match="no longer active"):
        old_callback()
    assert guard.status().samples == 0
    new_callback()
    new_callback()
    guard.finish(success=True)
    assert not guard.status().stopped


@pytest.mark.parametrize("field,value", [
    ("tokens", True), ("generation", True), ("bytes_reserved", True),
    ("lease_id", "not-hex"), ("checkpoint_digest", "x" * 64),
    ("request_id", chr(0xD800)),
])
def test_native_pressure_rejects_forged_permit_types_without_sampling(field, value):
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="canonical typed permit"):
        guard.start(replace(P, **{field: value}))
    assert guard.status().samples == 0


def test_native_pressure_guard_lifetime_capacity_is_bounded(monkeypatch):
    monkeypatch.setattr(pressure_module, "MAX_USED_LEASES", 1)
    probe(monkeypatch, [budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)
    callback()
    callback()
    guard.finish(success=True)
    with pytest.raises(NativePressureInterrupted, match="capacity"):
        guard.start(replace(P, lease_id="e" * 64, request_id="next"))
    assert guard.status().stopped


def test_forked_pressure_guard_rejects_inherited_callback_before_probe(monkeypatch):
    probe(monkeypatch, [budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)
    original = guard._owner_pid
    with monkeypatch.context() as scoped:
        scoped.setattr(pressure_module.os, "getpid", lambda: original + 1)
        with pytest.raises(NativePressureInterrupted, match="process identity changed"):
            callback()
        with pytest.raises(NativePressureInterrupted, match="process identity changed"):
            guard.finish(success=True)
        with pytest.raises(NativePressureInterrupted, match="process identity changed"):
            guard.status()
        with pytest.raises(NativePressureInterrupted, match="process identity changed"):
            guard.start(replace(P, lease_id="f" * 64))
    assert guard.status().stopped
    assert guard.status().samples == 0
    with pytest.raises(NativePressureInterrupted, match="not available"):
        guard.start(replace(P, lease_id="f" * 64))


def test_pressure_guard_rejects_unreadable_process_identity(monkeypatch):
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with monkeypatch.context() as scoped:
        scoped.setattr(pressure_module.os, "getpid", lambda: (_ for _ in ()).throw(OSError("pid unavailable")))
        with pytest.raises(NativePressureInterrupted, match="identity unavailable"):
            guard.start(P)
    assert guard.status().stopped
    assert guard.status().samples == 0

@pytest.mark.parametrize("mutation", [
    lambda e: e.pop("schema"),
    lambda e: e.pop("holds"),
    lambda e: e.update(cross_process_admission_guaranteed=True),
    lambda e: e["holds"].update(cgroup_oom=True),
    lambda e: e["holds"].update(thermal=True),
    lambda e: e["holds"].update(cgroup_swap_spill=True),
    lambda e: e.update(thermal_trip_measured="unknown"),
    lambda e: e["holds"].update(io=1),
])
def test_untrusted_live_pressure_evidence_quarantines_lease(monkeypatch, mutation):
    evidence = canonical_evidence()
    mutation(evidence)
    probe(monkeypatch, [budget()], evidence=evidence)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="untrusted OS pressure provenance"):
        guard.start(P)()
    assert guard.status().stopped
    assert guard.status().samples == 1


@pytest.mark.parametrize("change", ["missing", "soft_hold", "unknown_thermal"])
def test_ambiguous_pressure_never_grants_parallel_native_streams(monkeypatch, change):
    evidence = canonical_evidence()
    if change == "missing":
        evidence["auxiliary_telemetry_incomplete"] = True
    elif change == "soft_hold":
        evidence["auxiliary_telemetry_incomplete"] = False
        evidence["holds"]["cpu_throttle"] = True
    else:
        evidence["auxiliary_telemetry_incomplete"] = False
        evidence["thermal_trip_measured"] = False
    probe(monkeypatch, [budget(slots=2)], evidence=evidence)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="untrusted OS pressure provenance"):
        guard.start(P)()
    assert guard.status().stopped



@pytest.mark.parametrize("mutation", [
    lambda e: e.update(auxiliary_telemetry_incomplete=False,
                       cgroup_memory_limit_measured=False),
    lambda e: e.update(cgroup_swap_spill_allowed=True,
                       cgroup_swap_limit_measured=False),
    lambda e: e["holds"].update(cgroup_high=True),
    lambda e: e["holds"].update(swap_churn=True),
])
def test_inconsistent_pressure_floor_or_limit_evidence_denies(monkeypatch, mutation):
    evidence = canonical_evidence()
    mutation(evidence)
    probe(monkeypatch, [budget()], evidence=evidence)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="untrusted OS pressure provenance"):
        guard.start(P)()
    assert guard.status().stopped


@pytest.mark.parametrize("unknown", ["auxiliary", "thermal"])
def test_unknown_sensor_large_quantum_cannot_authorize_native_cpu(monkeypatch, unknown):
    evidence = canonical_evidence()
    if unknown == "thermal":
        evidence["auxiliary_telemetry_incomplete"] = False
        evidence["thermal_trip_measured"] = False
    probe(monkeypatch, [budget(tokens=256)], evidence=evidence)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with pytest.raises(NativePressureInterrupted, match="untrusted OS pressure provenance"):
        guard.start(P)()
    assert guard.status().stopped

def test_per_token_revalidation_preserves_original_ceiling_without_expanding_permit(monkeypatch):
    from skeleton.ai.model_runtime.fair_stream_revalidation import bound_revalidation_budget

    calls = []
    readings = iter((250_000, 250_000, 750_000))
    permit = replace(P, tokens=3)

    def sample(self, *, token_budget, storage_path):
        calls.append(token_budget)
        return budget(tokens=token_budget, pressure=next(readings)), canonical_evidence()

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    with bound_revalidation_budget(permit, 4):
        interrupt = guard.start(permit)
        interrupt()
        interrupt()
        with pytest.raises(NativePressureInterrupted, match="pressure hold"):
            interrupt()
        guard.finish(success=False)
    assert calls == [4, 4, 4]
    assert guard.status().stopped


def test_revalidation_scope_cannot_be_reused_for_another_permit():
    from skeleton.ai.model_runtime.fair_stream_revalidation import (
        bound_revalidation_budget, revalidation_budget,
    )

    other = replace(P)
    assert other == P and other is not P
    with bound_revalidation_budget(P, 10):
        assert revalidation_budget(P) == 10
        with pytest.raises(ValueError, match="does not bind"):
            revalidation_budget(other)
        with pytest.raises(ValueError, match="non-nested"):
            with bound_revalidation_budget(P, 12):
                pass
    assert revalidation_budget(P) == P.tokens

def test_exact_retired_lease_can_reauthorize_without_replaying_old_callback(monkeypatch):
    probe(monkeypatch, [budget(), budget(), budget()])
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    old = guard.start(P)
    old()
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="retired lease"):
        guard.reauthorize_retired_lease(replace(P, request_id="different"))
    guard.reauthorize_retired_lease(P)
    assert not guard.status().stopped
    next_permit = replace(P, lease_id="f" * 64, request_id="different", generation=2)
    current = guard.start(next_permit)
    with pytest.raises(NativePressureInterrupted, match="no longer active"):
        old()
    current()
    current()
    guard.finish(success=True)
    with pytest.raises(NativePressureInterrupted, match="replay"):
        guard.start(P)

def test_copied_context_cannot_resurrect_expired_planning_ceiling():
    from contextvars import copy_context
    from skeleton.ai.model_runtime.fair_stream_revalidation import (
        bound_revalidation_budget, revalidation_budget,
    )

    with bound_revalidation_budget(P, 8):
        copied = copy_context()
        assert copied.run(revalidation_budget, P) == 8
    with pytest.raises(ValueError, match="does not bind"):
        copied.run(revalidation_budget, P)
    assert revalidation_budget(P) == P.tokens


@pytest.mark.parametrize("nested", ["probe", "finish"])
def test_sampler_cannot_reenter_pressure_authority_even_if_error_swallowed(monkeypatch, nested):
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)

    def sample(self, *, token_budget, storage_path):
        with pytest.raises(NativePressureInterrupted, match="callback"):
            if nested == "probe":
                callback()
            else:
                guard.finish(success=True)
        return budget(), canonical_evidence()

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    with pytest.raises(NativePressureInterrupted, match="authority changed"):
        callback()
    assert guard.status().samples == 1
    assert guard._verified_samples == 0
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="retired lease"):
        guard.reauthorize_retired_lease(P)


def test_foreign_thread_cannot_sample_active_native_lease(monkeypatch):
    from threading import Thread

    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)
    errors = []

    def forbidden(*args, **kwargs):
        pytest.fail("foreign thread sampled native hardware")

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", forbidden)

    def attempt():
        try:
            callback()
        except NativePressureInterrupted as exc:
            errors.append(str(exc))

    thread = Thread(target=attempt)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and "foreign-thread" in errors[0]
    assert guard.status().samples == 0 and guard.status().stopped
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="retired lease"):
        guard.reauthorize_retired_lease(P)


def test_clock_regression_cannot_be_reauthorized_by_retirement(monkeypatch):
    values = iter((100, 99))
    monkeypatch.setattr(pressure_module, "monotonic_ns", lambda: next(values))
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    callback = guard.start(P)
    with pytest.raises(NativePressureInterrupted, match="clock regressed"):
        callback()
    guard.finish(success=False)
    with pytest.raises(NativePressureInterrupted, match="retired lease"):
        guard.reauthorize_retired_lease(P)
