import asyncio
import sys

import pytest

from skeleton.frontier.execution import ExecutionPolicy, ExecutionStatus
from skeleton.services.frontier import create_frontier_runtime
from skeleton.services.frontier_worker import run_operation


@pytest.mark.asyncio
async def test_existing_domain_pipelines_run_through_one_runtime(tmp_path):
    async with create_frontier_runtime(state_root=tmp_path) as runtime:
        npc, logic, review = await asyncio.gather(
            runtime.execute("gameforge.npc", "a loyal guardian", context={"name": "Sentinel"}),
            runtime.execute("gameforge.logic", "an exploration game with combat and progression"),
            runtime.execute("jeeves.review", "password = 'secret'\neval(user_input)"),
        )
        assert npc.succeeded and npc.output["name"] == "Sentinel"
        assert npc.output["dialogue_tree"] and npc.output["behaviour_graph"]
        assert logic.succeeded and logic.output["economy"]["taps"]
        assert review.succeeded and review.output["signals"]
        assert runtime.stats()["completed"] == 3


@pytest.mark.asyncio
async def test_worker_process_is_reaped_when_runtime_deadline_expires(tmp_path, monkeypatch):
    original = asyncio.create_subprocess_exec
    processes = []

    async def slow_worker(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_worker)
    async with create_frontier_runtime(state_root=tmp_path,
                                       execution_policy=ExecutionPolicy(execution_timeout=0.05)) as runtime:
        result = await runtime.execute("gameforge.npc", "guardian")
        assert result.status is ExecutionStatus.TIMED_OUT
        assert len(processes) == 1 and processes[0].returncode is not None
        assert runtime.stats()["active"] == 0


@pytest.mark.parametrize("operation,context", [
    ("gameforge.npc", {"dialogue_beats": True}),
    ("gameforge.logic", {"max_level": 1.5}),
    ("jeeves.review", {"language": []}),
    ("gameforge.npc", {"state_root": "/unexpected"}),
])
def test_worker_rejects_invalid_or_unrecognized_options(tmp_path, operation, context):
    with pytest.raises(ValueError):
        run_operation(operation, "task", context, tmp_path)
