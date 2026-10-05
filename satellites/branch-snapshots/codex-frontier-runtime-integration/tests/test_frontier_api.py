import asyncio

import httpx
import pytest
from fastapi import FastAPI

from skeleton.api.frontier_routes import router
from skeleton.api.hmac_seal import mint_seal
from skeleton.api.middleware import GatePolicy
from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.execution import ExecutionPolicy


class Echo:
    name = "echo"
    capabilities = set()

    def __init__(self):
        self.calls = 0

    async def run(self, task, context=None):
        self.calls += 1
        return {"task": task, "calls": self.calls}


def client_for(runtime):
    app = FastAPI()
    app.state.frontier_runtime = runtime
    app.include_router(router, prefix="/api/v1")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_api_requires_seal_and_keeps_idempotency_scoped_to_attester(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", "test-secret-only")
    agent = Echo()
    runtime = AgentRuntime({"echo": agent})
    headers = {"x-gf-seal": mint_seal("one"), "Idempotency-Key": "same"}
    async with client_for(runtime) as client:
        assert (
            await client.post("/api/v1/frontier/execute", json={"agent": "echo", "task": "work"})
        ).status_code == 401
        first = await client.post(
            "/api/v1/frontier/execute", headers=headers, json={"agent": "echo", "task": "work"}
        )
        replay = await client.post(
            "/api/v1/frontier/execute", headers=headers, json={"agent": "echo", "task": "work"}
        )
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json() and agent.calls == 1
        assert first.headers["X-Request-Id"] == first.json()["request_id"]
        assert (
            await client.post(
                "/api/v1/frontier/execute", headers=headers, json={"agent": "echo", "task": "changed"}
            )
        ).status_code == 409
        headers["x-gf-seal"] = mint_seal("two")
        assert (
            await client.post(
                "/api/v1/frontier/execute", headers=headers, json={"agent": "echo", "task": "work"}
            )
        ).status_code == 200
        assert agent.calls == 2


@pytest.mark.asyncio
async def test_api_maps_unknown_closed_and_invalid_requests(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", "test-secret-only")
    runtime = AgentRuntime({"echo": Echo()})
    headers = {"x-gf-seal": mint_seal("operator")}
    async with client_for(runtime) as client:
        assert (await client.get("/api/v1/frontier/agents", headers=headers)).json()["agents"][0][
            "name"
        ] == "echo"
        assert (
            await client.post(
                "/api/v1/frontier/execute", headers=headers, json={"agent": "missing", "task": "work"}
            )
        ).status_code == 404
        for body in [
            {"agent": "echo", "task": "work", "timeout": True},
            {"agent": "echo", "task": "work", "extra": 1},
        ]:
            assert (
                await client.post("/api/v1/frontier/execute", headers=headers, json=body)
            ).status_code == 422
        await runtime.aclose()
        assert (
            await client.post(
                "/api/v1/frontier/execute", headers=headers, json={"agent": "echo", "task": "work"}
            )
        ).status_code == 503


@pytest.mark.asyncio
async def test_timeout_result_has_504_status(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", "test-secret-only")

    class Blocked(Echo):
        async def run(self, task, context=None):
            await asyncio.Event().wait()

    runtime = AgentRuntime({"echo": Blocked()}, execution_policy=ExecutionPolicy(execution_timeout=0.01))
    async with client_for(runtime) as client:
        response = await client.post(
            "/api/v1/frontier/execute",
            headers={"x-gf-seal": mint_seal("operator")},
            json={"agent": "echo", "task": "work"},
        )
    assert response.status_code == 504
    assert response.json()["status"] == "timed_out"


def test_frontier_is_in_existing_sealed_governance_domain():
    policy = GatePolicy()
    assert policy.required_domain("/api/v1/frontier/execute") == "intelligence"
    assert not policy.is_open_route("/api/v1/frontier/execute")


def test_application_factory_mounts_runtime_routes_and_preserves_injection():
    from skeleton.api.server import create_app

    runtime = AgentRuntime()
    app = create_app(frontier_runtime=runtime)
    assert app.state.frontier_runtime is runtime
    assert "/api/v1/frontier/execute" in app.openapi()["paths"]
