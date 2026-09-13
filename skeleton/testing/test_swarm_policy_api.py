from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_policy_routes import AdmissionPreview, admission_preview, worker_ranking


def test_policy_preview_rejects_unroutable_capability() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("cpu", capabilities=["cpu"])
    body = AdmissionPreview(
        task_id="gpu",
        required_capabilities=["gpu"],
        require_capability_route=True,
    )
    result = admission_preview(body=body, runtime=runtime)
    assert result["accepted"] is False


def test_worker_ranking_orders_best_candidate_first() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("small", capabilities=["gpu"], capacity=1)
    runtime.register_worker("large", capabilities=["gpu"], capacity=4)
    runtime.submit(SwarmTask("job", {}, required_capabilities=frozenset({"gpu"})))
    result = worker_ranking("job", runtime=runtime)
    assert result["workers"][0]["worker_id"] == "large"
