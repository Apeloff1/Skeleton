"""Managed adapters for the existing GameForge and Jeeves implementations."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skeleton.frontier.agent_runtime import AgentFailure, AgentRuntime
from skeleton.frontier.capabilities import CapabilityPolicy
from skeleton.frontier.events import EventBus
from skeleton.frontier.execution import ExecutionPolicy
from skeleton.frontier.payloads import json_snapshot

OPERATIONS = {
    "gameforge.npc": "npc.generate",
    "gameforge.logic": "game_logic.generate",
    "jeeves.review": "code.review",
}


class PipelineAgent:
    """Run fixed local domain operations in a process that can be cancelled.

    Worker arguments select a built-in operation; task text is JSON data and
    is never evaluated as Python or shell code. The runtime owns admission.
    """

    def __init__(self, name: str, *, state_root: str | Path = ".skeleton") -> None:
        if name not in OPERATIONS:
            raise ValueError("unknown pipeline operation")
        self.name = name
        self.capabilities = frozenset({OPERATIONS[name]})
        self.state_root = Path(state_root).resolve()

    async def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any:
        payload = json_snapshot({"task": task, "context": dict(context or {})})
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "skeleton.services.frontier_worker",
            self.name,
            "--state-root",
            str(self.state_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await process.communicate(json.dumps(payload).encode("utf-8"))
            if process.returncode != 0:
                raise AgentFailure("local pipeline worker failed")
            if len(stdout) > 1_048_576:
                raise AgentFailure("local pipeline output exceeded its byte budget")
            return json.loads(stdout)
        finally:
            if process.returncode is None:
                process.kill()
                await process.communicate()


def create_frontier_runtime(
    *, state_root: str | Path = ".skeleton", execution_policy: ExecutionPolicy | None = None
) -> AgentRuntime:
    runtime = AgentRuntime(
        policy=CapabilityPolicy.from_names(OPERATIONS.values()),
        execution_policy=execution_policy,
        events=EventBus(),
    )
    for name in OPERATIONS:
        runtime.register(PipelineAgent(name, state_root=state_root))
    return runtime
