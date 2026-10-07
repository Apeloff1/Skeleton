from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api.swarm_broker_routes import BrokerCompletion, BrokerSubmission, complete, submit_and_dispatch


def test_completion_api_reports_duplicate_callback() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w")
    broker = SwarmBroker(runtime)
    submitted = submit_and_dispatch(BrokerSubmission(task_id="t"), broker=broker)
    assert submitted["leased"] is True

    first = complete("w", "t", BrokerCompletion(completion_token="callback-1"), broker=broker)
    second = complete("w", "t", BrokerCompletion(completion_token="callback-1"), broker=broker)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["state"] == "succeeded"
