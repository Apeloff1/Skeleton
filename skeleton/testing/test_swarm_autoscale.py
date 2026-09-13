from skeleton.agents.swarm_autoscale import AutoscalePolicy
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


def test_autoscale_scales_up_for_queue_demand() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=1)
    for i in range(10):
        runtime.submit(SwarmTask(str(i), {}))
    rec = AutoscalePolicy(target_tasks_per_slot=2).recommend(runtime)
    assert rec.current_slots == 1
    assert rec.desired_slots == 5
    assert rec.delta == 4


def test_autoscale_respects_maximum() -> None:
    runtime = SwarmRuntime()
    for i in range(100):
        runtime.submit(SwarmTask(str(i), {}))
    rec = AutoscalePolicy(target_tasks_per_slot=1, max_slots=7).recommend(runtime)
    assert rec.desired_slots == 7


def test_autoscale_scales_down_idle_capacity() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=10)
    rec = AutoscalePolicy(min_slots=1).recommend(runtime)
    assert rec.desired_slots == 1
    assert rec.delta == -9
