from __future__ import annotations

import pytest

from skeleton.reliability.long_horizon_aging import (
    AgingPolicy,
    GrowthBudget,
    LifecycleResource,
    LongHorizonAgingError,
    LongHorizonAgingGuard,
    SoakWindow,
)


def test_accelerated_time_schedule_is_deterministic_and_includes_horizon() -> None:
    values = LongHorizonAgingGuard.accelerated_times(
        start=100.0,
        horizon_seconds=25.0,
        step_seconds=10.0,
    )
    assert values == (100.0, 110.0, 120.0, 125.0)


def test_accelerated_time_rejects_zero_step_or_horizon() -> None:
    with pytest.raises(LongHorizonAgingError, match="positive"):
        LongHorizonAgingGuard.accelerated_times(
            start=0.0,
            horizon_seconds=10.0,
            step_seconds=0.0,
        )


def test_future_expiry_and_revalidation_are_detected() -> None:
    guard = LongHorizonAgingGuard()
    resources = (
        LifecycleResource(
            "api-cert",
            "certificate",
            activated_at=0.0,
            expires_at=100.0,
            revalidate_every_seconds=30.0,
        ),
    )
    report = guard.evaluate(
        resources,
        now=100.0,
        queue_depth=0,
        cache_entries=0,
        log_bytes=0,
        next_identifier=1,
        last_revalidated_at={"api-cert": 60.0},
    )
    assert report.expired == ("api-cert",)
    assert report.revalidation_due == ("api-cert",)
    assert report.safe is False


def test_retirement_requires_ready_replacement() -> None:
    guard = LongHorizonAgingGuard()
    resources = (
        LifecycleResource(
            "provider-v1",
            "provider",
            activated_at=0.0,
            retires_at=100.0,
            replacement="provider-v2",
        ),
    )
    blocked = guard.evaluate(
        resources,
        now=100.0,
        queue_depth=0,
        cache_entries=0,
        log_bytes=0,
        next_identifier=1,
    )
    assert blocked.retirement_due == ("provider-v1",)
    assert blocked.migration_blocked == ("provider-v1",)

    safe = guard.evaluate(
        resources,
        now=100.0,
        queue_depth=0,
        cache_entries=0,
        log_bytes=0,
        next_identifier=1,
        ready_replacements={"provider-v2"},
    )
    assert safe.retirement_due == ("provider-v1",)
    assert safe.migration_blocked == ()
    assert safe.safe is True


def test_model_retirement_mid_lifecycle_is_fail_closed_until_migrated() -> None:
    guard = LongHorizonAgingGuard()
    model = LifecycleResource(
        "model-a",
        "model",
        activated_at=10.0,
        retires_at=1_000.0,
        replacement="model-b",
    )
    report = guard.evaluate(
        (model,),
        now=10_000.0,
        queue_depth=0,
        cache_entries=0,
        log_bytes=0,
        next_identifier=1,
    )
    with pytest.raises(LongHorizonAgingError, match="migration_blocked"):
        guard.require_safe(report)


def test_resource_growth_bounds_cover_queue_cache_log_and_identifier() -> None:
    guard = LongHorizonAgingGuard(
        AgingPolicy(
            max_queue_depth=10,
            max_cache_entries=20,
            max_log_bytes=30,
            max_identifier=40,
        )
    )
    report = guard.evaluate(
        (),
        now=1.0,
        queue_depth=11,
        cache_entries=21,
        log_bytes=31,
        next_identifier=41,
    )
    assert report.bounds_exceeded == (
        "cache_entries:21>20",
        "log_bytes:31>30",
        "next_identifier:41>40",
        "queue_depth:11>10",
    )


def test_soak_window_accepts_bounded_stable_growth() -> None:
    window = SoakWindow()
    window.add_sample(at=0.0, metrics={"queue": 10, "cache": 100})
    window.add_sample(at=3600.0, metrics={"queue": 12, "cache": 120})
    report = window.evaluate(
        (
            GrowthBudget("queue", max_value=100, max_growth_per_hour=5.0),
            GrowthBudget("cache", max_value=1000, max_growth_per_hour=50.0),
        )
    )
    assert report.safe is True
    assert report.violations == ()


def test_soak_window_detects_slow_leak_before_absolute_exhaustion() -> None:
    window = SoakWindow()
    window.add_sample(at=0.0, metrics={"cache": 100})
    window.add_sample(at=7200.0, metrics={"cache": 500})
    report = window.evaluate(
        (GrowthBudget("cache", max_value=10_000, max_growth_per_hour=100.0),)
    )
    assert report.safe is False
    assert report.violations == (
        "cache:growth_per_hour:200.000000>100.000000",
    )


def test_soak_window_detects_missing_samples_and_absolute_bound() -> None:
    window = SoakWindow()
    window.add_sample(at=0.0, metrics={"queue": 10, "cache": 10})
    window.add_sample(at=3600.0, metrics={"queue": 200})
    report = window.evaluate(
        (
            GrowthBudget("queue", max_value=100, max_growth_per_hour=500.0),
            GrowthBudget("cache", max_value=100, max_growth_per_hour=500.0),
        )
    )
    assert "queue:max_value:200>100" in report.violations
    assert "cache:missing_sample" in report.violations


def test_soak_samples_must_be_strictly_monotonic_in_time() -> None:
    window = SoakWindow()
    window.add_sample(at=10.0, metrics={"queue": 1})
    with pytest.raises(LongHorizonAgingError, match="strictly increasing"):
        window.add_sample(at=10.0, metrics={"queue": 2})


def test_revalidation_timestamp_cannot_be_from_future() -> None:
    guard = LongHorizonAgingGuard()
    resource = LifecycleResource(
        "credential",
        "credential",
        activated_at=0.0,
        revalidate_every_seconds=10.0,
    )
    with pytest.raises(LongHorizonAgingError, match="revalidation time"):
        guard.evaluate(
            (resource,),
            now=20.0,
            queue_depth=0,
            cache_entries=0,
            log_bytes=0,
            next_identifier=1,
            last_revalidated_at={"credential": 21.0},
        )


def test_replacement_without_retirement_contract_is_rejected() -> None:
    with pytest.raises(LongHorizonAgingError, match="replacement requires"):
        LifecycleResource(
            "provider-v1",
            "provider",
            activated_at=0.0,
            replacement="provider-v2",
        )
