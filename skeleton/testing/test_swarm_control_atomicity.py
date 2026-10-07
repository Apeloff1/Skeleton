from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_control import SwarmControlPlane
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask


def test_failed_submission_does_not_poison_idempotency_key() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=1)
    runtime.submit(SwarmTask("existing", {}))
    control = SwarmControlPlane(runtime)

    with pytest.raises(AdmissionError):
        control.submit(SwarmTask("blocked", {"v": 1}), idempotency_key="k")

    assert control.idempotency.get("k") is None


def test_concurrent_idempotent_submission_creates_one_resident_task() -> None:
    runtime = HardenedSwarmRuntime()
    control = SwarmControlPlane(runtime)

    def submit():
        return control.submit(SwarmTask("task", {"v": 1}), idempotency_key="same")

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: submit(), range(64)))

    assert len(runtime.tasks()) == 1
    assert sum(not result.duplicate for result in results) == 1
    assert sum(result.duplicate for result in results) == 63


def test_idempotency_conflict_does_not_mutate_runtime() -> None:
    runtime = HardenedSwarmRuntime()
    control = SwarmControlPlane(runtime)
    control.submit(SwarmTask("task", {"v": 1}), idempotency_key="same")

    with pytest.raises(ValueError):
        control.submit(SwarmTask("task-2", {"v": 2}), idempotency_key="same")

    assert runtime.task("task") is not None
    assert runtime.task("task-2") is None
