from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys
import time
from uuid import uuid4

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    command_from_context,
)
from skeleton.provider_contract import ProviderToolDefinition

from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="container-boundary-policy",
        source_id="policy:container-boundary",
        content="Follow the container boundary smoke policy.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("container-boundary-smoke",),
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
        compiler_version="container-boundary-v1",
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
        compiler_version="container-boundary-v1",
    )


def _tool_definition() -> ProviderToolDefinition:
    return ProviderToolDefinition(
        tool_id="fixture.read",
        description="Read deterministic Stage-5 container fixture.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                }
            },
            "required": ["key"],
            "additionalProperties": False,
        },
    )


def _command(
    context: ContextEnvelope,
    *,
    started: datetime,
    expect_success_lineage: bool = False,
):
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="container-boundary-idem",
        instructions="Follow the container boundary smoke policy.",
        prompt="Return a bounded answer.",
        objective="Containerized engine boundary smoke",
        verification_profile=(
            "evidence_required"
            if expect_success_lineage
            else "assistant_proposal"
        ),
        service_principal="codedock-backend",
        created_at=started,
        deadline=started + timedelta(seconds=30),
        trace_id="trace-container-boundary",
        max_model_turns=2,
        max_tool_calls=2,
        max_repeat_tool_batches=1,
        tools=(
            (_tool_definition(),)
            if expect_success_lineage
            else ()
        ),
    )


async def _run(
    base_url: str,
    token: str,
    *,
    expect_success_lineage: bool = False,
) -> None:
    client = EngineClient(
        EngineClientConfig(
            base_url=base_url,
            service_token=token,
            service_principal="codedock-backend",
            request_timeout_s=5,
            execution_timeout_s=15,
        )
    )
    context = _context()
    started = _now()
    first = _command(
        context,
        started=started,
        expect_success_lineage=expect_success_lineage,
    )

    ack = await client.submit(first)
    if ack["operation_id"] != context.operation_id:
        raise AssertionError("container submit operation identity mismatch")
    if ack["execution_id"] != context.execution_id:
        raise AssertionError("container submit execution identity mismatch")

    retry = _command(
        context,
        started=started + timedelta(seconds=1),
        expect_success_lineage=expect_success_lineage,
    )
    if retry.submission_digest != first.submission_digest:
        raise AssertionError("container retry semantic digest drift")
    replay = await client.submit(retry)
    for field in ("operation_id", "execution_id", "idempotency_digest", "accepted_at"):
        if replay[field] != ack[field]:
            raise AssertionError("container retry changed " + field)

    with_error = False
    try:
        await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-b",
        )
    except EngineAuthorizationError:
        with_error = True
    if not with_error:
        raise AssertionError("container tenant mismatch was not denied")

    if expect_success_lineage:
        result = await client.wait_for_terminal(
            execution_id=context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            trace_id="trace-container-boundary",
            timeout_s=15,
        )
        if result.operation_id != context.operation_id:
            raise AssertionError("container result operation identity mismatch")
        if result.execution_id != context.execution_id:
            raise AssertionError("container result execution identity mismatch")
        if result.final_output != "containerized canonical answer":
            raise AssertionError("container final output mismatch")
        receipt = result.verification_receipt
        if not isinstance(receipt, dict) or receipt.get("outcome") != "passed":
            raise AssertionError("container verification receipt is missing")
        if receipt.get("verifier_id") != "container-boundary:independent":
            raise AssertionError("container verification identity mismatch")
        if result.evidence_refs != ("evidence:container-boundary",):
            raise AssertionError("container evidence lineage mismatch")
        if result.provider_receipts != (
            "provider:fake:container-provider-tool",
            "provider:fake:container-provider-final",
        ):
            raise AssertionError("container provider lineage mismatch")
        if len(result.tool_receipts) != 1:
            raise AssertionError("container tool receipt lineage mismatch")
        if result.stream_terminal_event is None:
            raise AssertionError("container terminal stream event is missing")
        if int(result.usage.get("tool_calls", -1)) != 1:
            raise AssertionError("container tool usage mismatch")

        events = await client.events(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            trace_id="trace-container-boundary",
        )
        terminal = [
            event
            for event in events.get("events", [])
            if event.get("type") == "execution.result"
        ]
        if len(terminal) != 1:
            raise AssertionError("container terminal result event is not unique")
        payload = terminal[0].get("result")
        if not isinstance(payload, dict):
            raise AssertionError("container terminal result payload is invalid")
        if payload.get("operation_id") != context.operation_id:
            raise AssertionError("container terminal operation lineage mismatch")
        if payload.get("execution_id") != context.execution_id:
            raise AssertionError("container terminal execution lineage mismatch")
        if payload.get("provider_receipts") != list(result.provider_receipts):
            raise AssertionError("container terminal provider receipts mismatch")
        if payload.get("tool_receipts") != list(result.tool_receipts):
            raise AssertionError("container terminal tool receipts mismatch")
        return

    # No provider credential is supplied to this smoke. The canonical
    # coordinator may therefore finish as provider_unavailable; that is an
    # expected fail-closed terminal state, not a transport failure.
    deadline = time.monotonic() + 10
    latest = None
    while time.monotonic() < deadline:
        latest = await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
        )
        if latest["execution_state"] in {"completed", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.05)
    if latest is None:
        raise AssertionError("container engine returned no status")
    if latest["operation_id"] != context.operation_id:
        raise AssertionError("container status operation identity mismatch")
    if latest["execution_id"] != context.execution_id:
        raise AssertionError("container status execution identity mismatch")
    if latest["execution_state"] not in {
        "admitted",
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
    }:
        raise AssertionError(
            "unexpected container engine state: "
            + str(latest["execution_state"])
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv("SKELETON_INTERNAL_URL", "http://127.0.0.1:8010"),
    )
    parser.add_argument(
        "--token",
        default=os.getenv("SKL_ENGINE_SERVICE_TOKEN", ""),
    )
    parser.add_argument(
        "--expect-success-lineage",
        action="store_true",
        default=os.getenv("STAGE5_EXPECT_SUCCESS_LINEAGE", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )
    args = parser.parse_args()
    if not args.token:
        print("engine container smoke requires service token", file=sys.stderr)
        return 2
    asyncio.run(
        _run(
            args.url.rstrip("/"),
            args.token,
            expect_success_lineage=args.expect_success_lineage,
        )
    )
    print("engine-container-boundary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
