"""Distributed authority dependency health proof tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.shells.ai.authority_health import (
    AIAuthorityHealthGuard,
    AuthorityHealthPolicy,
    AuthorityHealthResult,
    AuthorityHealthState,
    CallableAuthorityHealthProbe,
    VersionedStateHealthProbe,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)


class StaticProbe:
    def __init__(self, result: AuthorityHealthResult) -> None:
        self.result = result

    @property
    def name(self) -> str:
        return self.result.name

    def check(self) -> AuthorityHealthResult:
        return self.result


class BrokenGetStore(InMemoryFencedStore):
    def get(self, namespace, key):
        raise OSError("backend unavailable")


class ConflictStore(InMemoryFencedStore):
    def compare_and_swap(self, namespace, key, *, expected_revision, value):
        raise DistributedStateConflict("forced conflict")


def result(
    name="quorum",
    *,
    state=AuthorityHealthState.HEALTHY,
    checked_at=10.0,
    latency=0.01,
    detail="",
    revision=1,
):
    return AuthorityHealthResult(
        name,
        state,
        checked_at,
        latency,
        detail,
        revision,
    )


def test_health_result_happy_path():
    item = result()
    assert item.healthy
    assert item.to_dict()["state"] == "healthy"
    assert item.to_dict()["revision"] == 1


@pytest.mark.parametrize(
    "state",
    [AuthorityHealthState.DEGRADED, AuthorityHealthState.UNAVAILABLE],
)
def test_nonhealthy_states_are_not_healthy(state):
    assert not result(state=state).healthy


@pytest.mark.parametrize("name", ["", "x" * 129])
def test_health_result_rejects_invalid_name(name):
    with pytest.raises(ValueError, match="name"):
        result(name=name)


@pytest.mark.parametrize(
    "field,value",
    [
        ("checked_at", -1),
        ("latency_seconds", -1),
        ("checked_at", float("inf")),
        ("latency_seconds", float("nan")),
    ],
)
def test_health_result_rejects_invalid_time_values(field, value):
    values = dict(
        name="quorum",
        state=AuthorityHealthState.HEALTHY,
        checked_at=1.0,
        latency_seconds=0.1,
    )
    values[field] = value
    with pytest.raises(ValueError):
        AuthorityHealthResult(**values)


def test_health_result_rejects_bad_revision():
    with pytest.raises(ValueError, match="revision"):
        result(revision=0)


def test_health_result_metadata_is_immutable():
    item = AuthorityHealthResult(
        "quorum",
        AuthorityHealthState.HEALTHY,
        1,
        0.1,
        metadata={"mode": "rw"},
    )
    with pytest.raises(TypeError):
        item.metadata["mode"] = "tampered"


def test_callable_probe_true_is_healthy():
    probe = CallableAuthorityHealthProbe(
        "release",
        lambda: True,
        clock=lambda: 10,
        monotonic=iter([1.0, 1.2]).__next__,
    )
    item = probe.check()
    assert item.state is AuthorityHealthState.HEALTHY
    assert item.checked_at == 10
    assert item.latency_seconds == pytest.approx(0.2)


def test_callable_probe_false_is_unavailable():
    probe = CallableAuthorityHealthProbe(
        "release",
        lambda: False,
    )
    assert probe.check().state is AuthorityHealthState.UNAVAILABLE


def test_callable_probe_exception_is_sanitized():
    def broken():
        raise RuntimeError("secret backend detail")

    probe = CallableAuthorityHealthProbe("release", broken)
    item = probe.check()
    assert item.state is AuthorityHealthState.UNAVAILABLE
    assert item.detail == "probe raised RuntimeError"
    assert "secret backend detail" not in item.detail


def test_versioned_state_probe_write_heartbeat_proves_cas():
    backend = InMemoryFencedStore()
    probe = VersionedStateHealthProbe(
        "quorum",
        backend,
        instance_id="worker-a",
        clock=lambda: 10,
    )
    first = probe.check()
    second = probe.check()
    assert first.healthy
    assert second.healthy
    assert first.revision == 1
    assert second.revision == 2
    assert first.metadata["mode"] == "read-write-cas"


def test_versioned_state_probe_private_key_hides_raw_instance_id():
    probe = VersionedStateHealthProbe(
        "quorum",
        InMemoryFencedStore(),
        instance_id="worker-secret-name",
    )
    assert "worker-secret-name" not in probe.key
    assert probe.key.startswith("quorum:")
    assert len(probe.key.split(":", 1)[1]) == 32


def test_versioned_state_read_only_probe_does_not_create_heartbeat():
    backend = InMemoryFencedStore()
    probe = VersionedStateHealthProbe(
        "release",
        backend,
        instance_id="worker-a",
        require_write=False,
    )
    item = probe.check()
    assert item.healthy
    assert item.revision is None
    assert item.metadata["mode"] == "read"
    assert backend.records(probe.namespace) == ()


def test_versioned_state_probe_backend_exception_is_unavailable():
    probe = VersionedStateHealthProbe(
        "quorum",
        BrokenGetStore(),
        instance_id="worker-a",
    )
    item = probe.check()
    assert item.state is AuthorityHealthState.UNAVAILABLE
    assert item.detail == "backend probe raised OSError"


def test_versioned_state_probe_cas_conflict_is_degraded():
    probe = VersionedStateHealthProbe(
        "quorum",
        ConflictStore(),
        instance_id="worker-a",
    )
    item = probe.check()
    assert item.state is AuthorityHealthState.DEGRADED
    assert item.detail == "CAS heartbeat conflict"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "x" * 129},
        {"instance_id": ""},
        {"instance_id": "x" * 257},
        {"namespace": ""},
        {"require_write": "yes"},
    ],
)
def test_versioned_state_probe_constructor_validation(kwargs):
    values = dict(
        name="quorum",
        backend=InMemoryFencedStore(),
        instance_id="worker",
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        VersionedStateHealthProbe(**values)


def test_authority_health_policy_digest_is_deterministic():
    policy = AuthorityHealthPolicy(
        frozenset({"seal-replay", "quorum"}),
        max_latency_seconds=1,
        max_result_age_seconds=5,
    )
    assert len(policy.digest) == 64
    assert policy.digest == policy.digest
    assert policy.to_dict()["required"] == ["quorum", "seal-replay"]


def test_authority_health_policy_digest_changes_with_required_set():
    first = AuthorityHealthPolicy(frozenset({"quorum"}))
    second = AuthorityHealthPolicy(frozenset({"quorum", "seal"}))
    assert first.digest != second.digest


def test_authority_health_policy_digest_changes_with_latency():
    first = AuthorityHealthPolicy(
        frozenset({"quorum"}),
        max_latency_seconds=1,
    )
    second = AuthorityHealthPolicy(
        frozenset({"quorum"}),
        max_latency_seconds=2,
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_latency_seconds", 0),
        ("max_result_age_seconds", 0),
        ("max_latency_seconds", float("inf")),
    ],
)
def test_authority_health_policy_rejects_invalid_bounds(field, value):
    values = dict(
        required=frozenset({"quorum"}),
        max_latency_seconds=1,
        max_result_age_seconds=1,
    )
    values[field] = value
    with pytest.raises(ValueError):
        AuthorityHealthPolicy(**values)


def test_guard_requires_configured_required_probes():
    with pytest.raises(ValueError, match="missing"):
        AIAuthorityHealthGuard(
            (),
            AuthorityHealthPolicy(frozenset({"quorum"})),
        )


def test_guard_rejects_duplicate_probe_names():
    one = StaticProbe(result("quorum"))
    two = StaticProbe(result("quorum"))
    with pytest.raises(ValueError, match="duplicate"):
        AIAuthorityHealthGuard(
            (one, two),
            AuthorityHealthPolicy(frozenset({"quorum"})),
        )


def test_guard_happy_path():
    guard = AIAuthorityHealthGuard(
        (
            StaticProbe(result("quorum", checked_at=10)),
            StaticProbe(result("seal", checked_at=10)),
        ),
        AuthorityHealthPolicy(
            frozenset({"quorum", "seal"}),
            max_latency_seconds=1,
            max_result_age_seconds=5,
        ),
        clock=lambda: 10,
    )
    report = guard.require()
    assert report.ok
    assert not report.reasons
    assert guard.last_report == report


@pytest.mark.parametrize(
    "state",
    [AuthorityHealthState.DEGRADED, AuthorityHealthState.UNAVAILABLE],
)
def test_required_nonhealthy_dependency_blocks(state):
    guard = AIAuthorityHealthGuard(
        (StaticProbe(result("quorum", state=state)),),
        AuthorityHealthPolicy(frozenset({"quorum"})),
        clock=lambda: 10,
    )
    report = guard.inspect()
    assert not report.ok
    assert state.value in report.reasons[0]
    with pytest.raises(RuntimeError, match="quorum"):
        guard.require()


def test_optional_nonhealthy_dependency_does_not_block():
    guard = AIAuthorityHealthGuard(
        (
            StaticProbe(result("quorum")),
            StaticProbe(
                result(
                    "telemetry",
                    state=AuthorityHealthState.UNAVAILABLE,
                )
            ),
        ),
        AuthorityHealthPolicy(frozenset({"quorum"})),
        clock=lambda: 10,
    )
    report = guard.inspect()
    assert report.ok
    assert report.reasons == ()


def test_required_latency_overrun_blocks_even_if_probe_says_healthy():
    guard = AIAuthorityHealthGuard(
        (StaticProbe(result("quorum", latency=2.0)),),
        AuthorityHealthPolicy(
            frozenset({"quorum"}),
            max_latency_seconds=1.0,
        ),
        clock=lambda: 10,
    )
    report = guard.inspect()
    assert not report.ok
    assert any("latency" in reason for reason in report.reasons)


def test_required_stale_result_blocks():
    guard = AIAuthorityHealthGuard(
        (StaticProbe(result("quorum", checked_at=1.0)),),
        AuthorityHealthPolicy(
            frozenset({"quorum"}),
            max_result_age_seconds=5.0,
        ),
        clock=lambda: 10.0,
    )
    report = guard.inspect()
    assert not report.ok
    assert any("stale" in reason for reason in report.reasons)


def test_future_checked_time_does_not_create_negative_age_failure():
    guard = AIAuthorityHealthGuard(
        (StaticProbe(result("quorum", checked_at=11.0)),),
        AuthorityHealthPolicy(
            frozenset({"quorum"}),
            max_result_age_seconds=1.0,
        ),
        clock=lambda: 10.0,
    )
    assert guard.inspect().ok


def test_report_is_stably_sorted_by_probe_name():
    guard = AIAuthorityHealthGuard(
        (
            StaticProbe(result("zeta")),
            StaticProbe(result("alpha")),
        ),
        AuthorityHealthPolicy(frozenset()),
        clock=lambda: 10,
    )
    report = guard.inspect()
    assert [item.name for item in report.results] == ["alpha", "zeta"]


def test_report_to_dict_contains_policy_identity():
    policy = AuthorityHealthPolicy(frozenset({"quorum"}))
    guard = AIAuthorityHealthGuard(
        (StaticProbe(result("quorum")),),
        policy,
        clock=lambda: 10,
    )
    data = guard.inspect().to_dict()
    assert data["ok"] is True
    assert data["policy_digest"] == policy.digest
    assert data["observed_at"] == 10


def test_real_backend_guard_advances_heartbeat_each_check():
    backend = InMemoryFencedStore()
    probe = VersionedStateHealthProbe(
        "seal-replay",
        backend,
        instance_id="worker",
    )
    guard = AIAuthorityHealthGuard(
        (probe,),
        AuthorityHealthPolicy(frozenset({"seal-replay"})),
    )
    first = guard.require()
    second = guard.require()
    assert first.results[0].revision == 1
    assert second.results[0].revision == 2


def test_required_backend_failure_is_fail_closed():
    probe = VersionedStateHealthProbe(
        "seal-replay",
        BrokenGetStore(),
        instance_id="worker",
    )
    guard = AIAuthorityHealthGuard(
        (probe,),
        AuthorityHealthPolicy(frozenset({"seal-replay"})),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        guard.require()


def test_required_cas_conflict_is_fail_closed():
    probe = VersionedStateHealthProbe(
        "quorum",
        ConflictStore(),
        instance_id="worker",
    )
    guard = AIAuthorityHealthGuard(
        (probe,),
        AuthorityHealthPolicy(frozenset({"quorum"})),
    )
    with pytest.raises(RuntimeError, match="degraded"):
        guard.require()


def test_policy_allows_observational_optional_probes():
    guard = AIAuthorityHealthGuard(
        (
            CallableAuthorityHealthProbe("metrics", lambda: False),
            CallableAuthorityHealthProbe("tracing", lambda: False),
        ),
        AuthorityHealthPolicy(frozenset()),
    )
    assert guard.require().ok


def test_health_metadata_never_contains_raw_backend_exception():
    class SecretStore(InMemoryFencedStore):
        def get(self, namespace, key):
            raise RuntimeError("token=super-secret")

    item = VersionedStateHealthProbe(
        "quorum",
        SecretStore(),
        instance_id="worker",
    ).check()
    raw = str(item.to_dict())
    assert "super-secret" not in raw
    assert "RuntimeError" in raw


def test_health_policy_rejects_too_many_required_dependencies():
    with pytest.raises(ValueError, match="bound"):
        AuthorityHealthPolicy(
            frozenset(f"dep-{index}" for index in range(65))
        )


def test_health_guard_rejects_too_many_probes():
    probes = tuple(
        StaticProbe(result(f"dep-{index}"))
        for index in range(65)
    )
    with pytest.raises(ValueError, match="bound"):
        AIAuthorityHealthGuard(
            probes,
            AuthorityHealthPolicy(frozenset()),
        )
