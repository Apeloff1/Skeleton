"""Cross-subsystem integration coverage for the canonical frontier paths.

Each test name spells out the boundary chain so failures identify the seam that
regressed rather than presenting as a generic end-to-end failure.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import skeleton.api.server as api_server  # noqa: E402
from skeleton.api.correlation import run_with_request_correlation  # noqa: E402
from skeleton.api.hmac_seal import mint_seal  # noqa: E402
from skeleton.frontier.orchestration import (  # noqa: E402
    OrchestrationDriver,
    RunRecord,
    RunStatus,
    ToolInvocation,
    ToolRegistry,
    ToolResult,
    TurnOutcome,
)
from skeleton.observability.orchestration import ObservableOrchestrator  # noqa: E402


_SECRET = "integration-matrix-seal-secret"


@pytest.fixture
def api_client(monkeypatch):
    """Boot the real API/Genesis stack with deterministic local-only credentials."""
    monkeypatch.setenv("GF_SEAL_SECRET", _SECRET)
    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    api_server._state = None
    with TestClient(api_server.create_app()) as client:
        yield client
    api_server._state = None


def _sealed_headers(*, request_id: str = "matrix-request-1") -> dict[str, str]:
    return {
        "x-gf-seal": mint_seal("integration-matrix", secret=_SECRET),
        "x-request-id": request_id,
    }


def test_boundary_api__retrieval__rag__fusion__provenance_happy_path(api_client) -> None:
    """HTTP -> gate -> Genesis -> QuadRetriever -> RAG -> fusion -> provenance."""
    headers = _sealed_headers(request_id="matrix-retrieval-1")
    metadata = {
        "source_repository": "Apeloff1/Skeleton",
        "source_revision": "integration-fixture",
        "source_path": "tests/fixtures/integration-matrix.txt",
    }
    ingest = api_client.post(
        "/api/v1/retrieval/ingest",
        headers=headers,
        json={
            "doc_id": "matrix-doc-1",
            "text": "alpha boundary citation source",
            "metadata": metadata,
        },
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.headers["x-request-id"] == "matrix-retrieval-1"
    assert ingest.json()["chunks"] == 1

    query = api_client.post(
        "/api/v1/retrieval/query",
        headers=_sealed_headers(request_id="matrix-retrieval-2"),
        json={"query": "alpha boundary", "k": 4, "use_cache": False},
    )
    assert query.status_code == 200, query.text
    assert query.headers["x-request-id"] == "matrix-retrieval-2"

    hits = query.json()["results"]
    hit = next(item for item in hits if item["id"] == "matrix-doc-1")
    assert hit["plane"] == "rag"
    assert hit["content"] == "alpha boundary citation source"
    assert hit["provenance"] == (
        "Apeloff1/Skeleton@integration-fixture:tests/fixtures/integration-matrix.txt"
    )


def test_boundary_api_gate__retrieval_state_rejects_invalid_seal_without_mutation(api_client) -> None:
    """Gate failure must stop before retrieval storage is mutated."""
    blocked = api_client.post(
        "/api/v1/retrieval/ingest",
        headers={"x-gf-seal": "invalid", "x-request-id": "matrix-blocked"},
        json={
            "doc_id": "matrix-blocked-doc",
            "text": "blocked mutation sentinel",
        },
    )
    assert blocked.status_code == 401
    assert blocked.headers["x-request-id"] == "matrix-blocked"

    query = api_client.post(
        "/api/v1/retrieval/query",
        headers=_sealed_headers(request_id="matrix-after-block"),
        json={"query": "blocked mutation sentinel", "k": 20, "use_cache": False},
    )
    assert query.status_code == 200, query.text
    assert all(item["id"] != "matrix-blocked-doc" for item in query.json()["results"])


class _Headers:
    def __init__(self, request_id: str) -> None:
        self._request_id = request_id

    def getlist(self, name: str) -> list[str]:
        return [self._request_id] if name.lower() == "x-request-id" else []


class _Request:
    def __init__(self, request_id: str) -> None:
        self.headers = _Headers(request_id)
        self.state = SimpleNamespace()


class _StateWriteDriver(OrchestrationDriver):
    def __init__(self) -> None:
        self._requested = False

    async def next_turn(
        self,
        *,
        run: RunRecord,
        tool_results: tuple[ToolResult, ...],
    ) -> TurnOutcome:
        del run
        if not self._requested:
            self._requested = True
            return TurnOutcome(
                tool_calls=(
                    ToolInvocation(
                        call_id="matrix-call-1",
                        name="write_state",
                        arguments={"key": "phase", "value": "integrated"},
                    ),
                )
            )
        assert len(tool_results) == 1
        return TurnOutcome(output=tool_results[0].output, terminal=True)


def test_boundary_api_correlation__orchestrator__tool__state_happy_path() -> None:
    """API request context -> orchestrator -> registered tool -> durable run state."""

    async def scenario() -> None:
        state: dict[str, str] = {}
        tools = ToolRegistry()

        def write_state(arguments):
            state[str(arguments["key"])] = str(arguments["value"])
            return dict(state)

        tools.register("write_state", write_state)
        orchestrator = ObservableOrchestrator(tools=tools)
        request = _Request("matrix-orchestration-request")

        record = await run_with_request_correlation(
            orchestrator,
            request,
            _StateWriteDriver(),
            run_id="matrix-run-1",
        )

        assert record.status is RunStatus.COMPLETED
        assert record.output == {"phase": "integrated"}
        assert state == {"phase": "integrated"}
        assert request.state.request_id == "matrix-orchestration-request"
        assert {event.correlation_id for event in orchestrator.metrics_bridge.events()} == {
            "matrix-orchestration-request"
        }

    asyncio.run(scenario())