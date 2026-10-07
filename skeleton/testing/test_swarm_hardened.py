from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import AdmissionError, LeaseError, SwarmTask


def test_worker_capacity_is_enforced_inside_runtime() -> None:
    runtime = HardenedSwarmRuntime(max_workers=1)
    runtime.register_worker("a")
    with pytest.raises(AdmissionError, match="worker capacity"):
        runtime.register_worker("b")


def test_lease_renewal_limit_is_enforced_inside_runtime() -> None:
    runtime = HardenedSwarmRuntime(max_lease_seconds=60)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    runtime.lease("w")
    with pytest.raises(LeaseError, match="max_lease_seconds"):
        runtime.renew("w", "t", seconds=61)


def test_task_and_worker_ids_are_normalized() -> None:
    runtime = HardenedSwarmRuntime()
    worker = runtime.register_worker("  w  ")
    task = runtime.submit(SwarmTask("  t  ", {}))
    assert worker.id == "w"
    assert task.id == "t"
    assert runtime.worker(" w ") is worker
    assert runtime.task(" t ") is task


def test_parallel_duplicate_worker_admission_is_fail_closed() -> None:
    runtime = HardenedSwarmRuntime()

    def register() -> str:
        try:
            runtime.register_worker("same")
            return "accepted"
        except AdmissionError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: register(), range(64)))
    assert results.count("accepted") == 1
    assert results.count("rejected") == 63


def test_parallel_task_admission_preserves_max_tasks() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=10)

    def submit(index: int) -> bool:
        try:
            runtime.submit(SwarmTask(str(index), {}))
            return True
        except AdmissionError:
            return False

    with ThreadPoolExecutor(max_workers=32) as pool:
        accepted = list(pool.map(submit, range(100)))
    assert sum(accepted) == 10
    assert len(runtime.tasks()) == 10


def test_export_persists_hardening_configuration() -> None:
    runtime = HardenedSwarmRuntime(max_workers=12, max_lease_seconds=123)
    config = runtime.export_state()["config"]
    assert config["max_workers"] == 12
    assert config["max_lease_seconds"] == 123
