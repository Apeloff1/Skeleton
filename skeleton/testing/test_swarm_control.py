import pytest

from skeleton.agents.swarm_admission import AdmissionPolicy
from skeleton.agents.swarm_control import SwarmControlPlane
from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, SwarmTask, TaskState


def test_control_plane_idempotent_submit_returns_resident_task() -> None:
    runtime = SwarmRuntime()
    control = SwarmControlPlane(runtime)
    first = control.submit(SwarmTask("a", {"x": 1}), idempotency_key="k")
    second = control.submit(SwarmTask("a", {"x": 1}), idempotency_key="k")
    assert first.task.id == second.task.id == "a"
    assert second.duplicate is True
    assert len(runtime.tasks()) == 1


def test_control_plane_enforces_admission_policy() -> None:
    runtime = SwarmRuntime()
    policy = AdmissionPolicy(reject_when_no_workers=True)
    control = SwarmControlPlane(runtime, admission=policy)
    with pytest.raises(AdmissionError):
        control.submit(SwarmTask("a", {}))


def test_control_plane_ranks_and_leases_best_worker() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("small", capabilities=["gpu"], capacity=1)
    runtime.register_worker("large", capabilities=["gpu"], capacity=4)
    control = SwarmControlPlane(runtime)
    control.submit(SwarmTask("job", {}, required_capabilities=frozenset({"gpu"})))
    ranked = control.rank_workers("job")
    assert ranked[0].worker_id == "large"
    leased = control.lease_best("job")
    assert leased is not None
    assert leased.state is TaskState.LEASED
    assert leased.leased_to == "large"
