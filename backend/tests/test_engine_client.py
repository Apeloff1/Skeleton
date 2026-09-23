from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error

import pytest

from core.engine_client import (
    EngineClient,
    EngineClientConfig,
    EngineRequestConflict,
    engine_command_from_provider_request,
)
from skeleton.provider_runtime import AIMessage, ProviderRequest


ROOT = Path(__file__).resolve().parents[2]


class _Response:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _size=-1):
        return self.payload


def _client() -> EngineClient:
    return EngineClient(
        EngineClientConfig(
            base_url="http://engine.test:8001",
            service_principal="codedock-backend",
            seal_secret="test-seal-secret",
            timeout_seconds=2,
            retry_attempts=2,
            poll_interval_seconds=0.001,
        )
    )


@pytest.mark.asyncio
async def test_engine_client_execute_uses_sealed_submit_status_and_result_events(
    monkeypatch,
) -> None:
    client = _client()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    command = engine_command_from_provider_request(
        ProviderRequest(
            instructions="rules",
            prompt="hello",
            history=(AIMessage(role="user", content="older"),),
            tenant_id="tenant-a",
            purpose="model-inference",
        ),
        service_principal=client.config.service_principal,
        deadline=deadline,
    )
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "headers": dict(request.header_items()),
                "body": (
                    None
                    if request.data is None
                    else json.loads(request.data.decode("utf-8"))
                ),
                "timeout": timeout,
            }
        )
        if request.get_method() == "POST":
            return _Response(
                {
                    "execution_id": command.execution_request.execution_id,
                    "operation_id": command.operation.operation_id,
                    "state": "admitted",
                }
            )
        if request.full_url.endswith("/events"):
            return _Response(
                {
                    "execution_id": command.execution_request.execution_id,
                    "events": [
                        {
                            "type": "execution.result",
                            "result": {
                                "status": "completed",
                                "final_output": "engine answer",
                                "verification": "verification:1",
                                "verification_receipt": {
                                    "outcome": "verified"
                                },
                                "evidence_refs": [],
                                "usage": {
                                    "model_turns": 1,
                                    "tool_calls": 0,
                                },
                            },
                        }
                    ],
                }
            )
        return _Response(
            {
                "execution_id": command.execution_request.execution_id,
                "operation_state": "completed",
                "execution_state": "completed",
            }
        )

    monkeypatch.setattr(
        "core.engine_client.urllib.request.urlopen",
        fake_urlopen,
    )

    result = await client.execute(command, deadline=deadline)

    assert result["final_output"] == "engine answer"
    assert [call["method"] for call in calls] == ["POST", "GET", "GET"]
    submit = calls[0]
    assert submit["url"].endswith("/api/v1/engine/executions")
    assert submit["body"]["command"]["compiled_context"]["prompt"] == "hello"
    assert submit["body"]["command"]["compiled_context"]["history"] == [
        {"role": "user", "content": "older"}
    ]
    headers = {key.lower(): value for key, value in submit["headers"].items()}
    assert headers["x-gf-seal"]
    assert "openai" not in json.dumps(submit["body"]).lower()


@pytest.mark.asyncio
async def test_engine_client_maps_submit_conflict_without_retry(monkeypatch) -> None:
    client = _client()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    command = engine_command_from_provider_request(
        ProviderRequest(instructions="rules", prompt="hello"),
        service_principal=client.config.service_principal,
        deadline=deadline,
    )
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            request.full_url,
            409,
            "Conflict",
            {},
            _Response({"detail": "idempotency conflict"}),
        )

    monkeypatch.setattr(
        "core.engine_client.urllib.request.urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        EngineRequestConflict,
        match="idempotency conflict",
    ):
        await client.submit(command, deadline=deadline)

    assert calls == 1


def test_compose_moves_provider_credentials_to_engine_process_only() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    skeleton_block = compose.split("  skeleton:", 1)[1].split(
        "  backend:", 1
    )[0]
    backend_block = compose.split("  backend:", 1)[1].split(
        "  frontend:", 1
    )[0]

    assert "OPENAI_API_KEY=" in skeleton_block
    assert "AI_PROVIDER=" in skeleton_block
    assert "GF_SEAL_SECRET=" in skeleton_block
    assert "SKL_ENGINE_EXECUTION_STATE_PATH=" in skeleton_block
    assert "SKL_ENGINE_SUBMISSION_STATE_PATH=" in skeleton_block
    assert "SKL_ENGINE_TOOL_RECEIPT_PATH=" in skeleton_block

    assert "OPENAI_API_KEY=" not in backend_block
    assert "EMERGENT_LLM_KEY=" not in backend_block
    assert "GF_SEAL_SECRET=" in backend_block
    assert "SKELETON_INTERNAL_URL=" in backend_block
    assert "CODEDOCK_ENGINE_SERVICE_PRINCIPAL=" in backend_block
