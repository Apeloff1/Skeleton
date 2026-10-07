from __future__ import annotations

import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.api.swarm_routes import WorkerRegistration, register_worker


def test_duplicate_worker_registration_is_conflict() -> None:
    runtime = SwarmRuntime()
    body = WorkerRegistration(worker_id="worker-1", capabilities=["python"], capacity=2)
    register_worker(body, runtime)

    with pytest.raises(HTTPException) as exc:
        register_worker(body, runtime)

    assert exc.value.status_code == 409
    assert runtime.worker("worker-1") is not None
    assert runtime.worker("worker-1").capacity == 2


def test_invalid_worker_capacity_is_rejected_by_schema() -> None:
    with pytest.raises(Exception):
        WorkerRegistration(worker_id="worker-1", capacity=0)
