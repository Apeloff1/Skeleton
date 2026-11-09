from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_batch import submit_batch
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask


def test_native_batch_admission_is_all_or_none() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=3)
    runtime.submit(SwarmTask("existing", {}))
    with pytest.raises(AdmissionError):
        submit_batch(runtime, [SwarmTask("a", {}), SwarmTask("b", {}), SwarmTask("c", {})])
    assert {task.id for task in runtime.tasks()} == {"existing"}


def test_native_batch_normalizes_ids_and_preserves_order() -> None:
    runtime = HardenedSwarmRuntime()
    result = submit_batch(runtime, [SwarmTask(" a ", {}), SwarmTask("b", {})])
    assert result.task_ids == ("a", "b")
    assert [task.id for task in runtime.tasks()] == ["a", "b"]


def test_competing_batches_cannot_overcommit_capacity() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=4)

    def submit(prefix: str):
        try:
            return submit_batch(runtime, [SwarmTask(f"{prefix}-1", {}), SwarmTask(f"{prefix}-2", {}), SwarmTask(f"{prefix}-3", {})])
        except AdmissionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["a", "b"]))

    assert sum(result is not None for result in results) == 1
    assert len(runtime.tasks()) == 3
