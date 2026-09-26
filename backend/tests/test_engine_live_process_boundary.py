from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    command_from_context,
)
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)


ROOT = Path(__file__).resolve().parents[2]
_SERVICE_TOKEN = "live-process-engine-token-" + ("x" * 40)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="live-process-policy",
        source_id="policy:live-process",
        content="Follow the live-process test policy.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("live-process-test",),
        retention_class="policy",
        mandatory=True,
    )
    budget = ContextBudget(
        max_context_tokens=4096,
        reserved_output_tokens=512,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=512,
        safety_margin_tokens=128,
        max_segment_tokens=2048,
        max_artifact_tokens=1024,
        max_tool_result_tokens=1024,
    )
    digest = context_digest_payload(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        budget=budget,
        selected=(segment,),
        omitted_segment_ids=(),
        compiler_version="live-process-v1",
    )
    return ContextEnvelope(
        context_id=str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        instruction_segments=(segment,),
        evidence_segments=(),
        tool_schema_segments=(),
        budget=budget,
        selected_tokens_estimate=segment.token_estimate,
        omitted_segment_ids=(),
        omission_reasons=(),
        source_snapshot=((segment.segment_id, segment.content_digest),),
        context_digest=digest,
        compiled_at=_now(),
        compiler_version="live-process-v1",
    )


def _command(context: ContextEnvelope, *, started: datetime):
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="live-process-idem",
        instructions="Follow the live-process test policy.",
        prompt="Return a bounded answer.",
        objective="Live engine process boundary test",
        verification_profile="assistant_proposal",
        service_principal="codedock-backend",
        created_at=started,
        deadline=started + timedelta(seconds=20),
        trace_id="trace-live-process",
        max_model_turns=2,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(base_url: str, process: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            response = httpx.get(base_url + "/healthz", timeout=0.25)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    log = log_path.read_text(encoding="utf-8", errors="replace")
    raise AssertionError(
        "live engine process did not become ready; exit="
        + str(process.poll())
        + "\n"
        + log[-8000:]
    )


@pytest.mark.asyncio
async def test_engine_client_crosses_real_tcp_process_boundary(tmp_path) -> None:
    port = _free_port()
    base_url = "http://127.0.0.1:" + str(port)
    log_path = tmp_path / "engine-process.log"
    env = dict(os.environ)
    env.update(
        {
            "TEST_ENGINE_EXECUTION_PATH": str(tmp_path / "execution.sqlite3"),
            "TEST_ENGINE_SUBMISSION_PATH": str(tmp_path / "submission.sqlite3"),
            "TEST_ENGINE_SERVICE_TOKEN": _SERVICE_TOKEN,
            "PYTHONUNBUFFERED": "1",
        }
    )

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "skeleton.testing.live_engine_process_app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_ready(base_url, process, log_path)

            client = EngineClient(
                EngineClientConfig(
                    base_url=base_url,
                    service_token=_SERVICE_TOKEN,
                    service_principal="codedock-backend",
                    request_timeout_s=2,
                    execution_timeout_s=10,
                )
            )
            context = _context()
            started = _now()
            first = _command(context, started=started)
            ack = await client.submit(first)

            assert ack["operation_id"] == context.operation_id
            assert ack["execution_id"] == context.execution_id
            assert ack["state"] == "created"

            retry = _command(
                context,
                started=started + timedelta(seconds=1),
            )
            assert retry.command_digest != first.command_digest
            assert retry.submission_digest == first.submission_digest
            replay = await client.submit(retry)
            assert replay["execution_id"] == ack["execution_id"]
            assert replay["idempotency_digest"] == ack["idempotency_digest"]
            assert replay["accepted_at"] == ack["accepted_at"]

            status = await client.status(
                context.execution_id,
                actor_id="actor-a",
                tenant_id="tenant-a",
            )
            assert status["execution_state"] == "created"
            assert status["cancellation_requested"] is False

            with pytest.raises(EngineAuthorizationError):
                await client.status(
                    context.execution_id,
                    actor_id="actor-a",
                    tenant_id="tenant-b",
                )

            cancelled = await client.cancel(
                context.execution_id,
                actor_id="actor-a",
                tenant_id="tenant-a",
                reason="live process boundary cancellation",
            )
            assert cancelled["cancellation_requested"] is True

            final_status = await client.status(
                context.execution_id,
                actor_id="actor-a",
                tenant_id="tenant-a",
            )
            assert final_status["cancellation_requested"] is True
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
