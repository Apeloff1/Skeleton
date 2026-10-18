"""Versioned subsystem boundaries reject malformed envelopes."""

from __future__ import annotations

import pytest

from skeleton.contracts.health import parse_liveness, parse_readiness
from skeleton.contracts.subsystem_boundaries import (
    SUBSYSTEM_CONTRACTS,
    SUBSYSTEM_CONTRACT_VERSION,
    AgentTaskBoundary,
    ApiErrorBoundary,
    GameForgeCommandBoundary,
    KernelEventBoundary,
    MemoryWriteBoundary,
    SubsystemContractError,
)


DIGEST = "a" * 64


def test_published_subsystem_set_is_stable() -> None:
    assert set(SUBSYSTEM_CONTRACTS) == {"kernel", "agents", "memory", "gameforge", "api"}
    assert all(item.version == SUBSYSTEM_CONTRACT_VERSION for item in SUBSYSTEM_CONTRACTS.values())


def test_boundaries_accept_canonical_values() -> None:
    assert KernelEventBoundary(event_type="boot", payload_digest=DIGEST).schema_version == "1.0.0"
    assert AgentTaskBoundary(task_id="task-1", capability="plan", payload_digest=DIGEST).capability == "plan"
    assert MemoryWriteBoundary(memory_id="mem-1", kind="episodic", content_digest=DIGEST).kind == "episodic"
    command = GameForgeCommandBoundary(command="run", request_digest=DIGEST)
    assert command.command == "run"
    envelope = ApiErrorBoundary(code="SKL.INTERNAL", message="internal server error").as_dict()
    assert envelope["error"]["context"] == {}


def test_gameforge_facade_rejects_pipeline_commands() -> None:
    with pytest.raises(SubsystemContractError):
        GameForgeCommandBoundary(command="materialise", request_digest=DIGEST)


def test_health_contract_reads_existing_payloads() -> None:
    assert parse_liveness({"alive": True, "timestamp": 1}).alive is True
    ready = parse_readiness({"ready": False, "status": "degraded", "checks": 3})
    assert ready.ready is False
    assert ready.status == "degraded"
    with pytest.raises(Exception):
        parse_liveness({"alive": "yes"})
