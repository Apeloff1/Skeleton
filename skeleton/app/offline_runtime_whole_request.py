"""Connect measured offline admission to the existing whole-request engine.

This adapter is intentionally distinct from the incremental SliceExecutor.
A backend that implements only LocalInferenceEngine.generate is not treated
as a token-sliced decoder. A trusted host supplies the actual engine and
independently pinned backend identity; no provider or backend is selected
from an external request.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any

from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine, LocalInferenceRequest, LocalInferenceResult,
)
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase, IterationWork
from skeleton.app.offline_runtime_preflight import RuntimePreflightError, digest, identity, integer, require
from skeleton.app.offline_runtime_session import OfflineRuntimeSession


@dataclass(frozen=True, slots=True)
class WholeRequestOutcome:
    receipt: dict
    result: LocalInferenceResult | None


class MeasuredWholeRequestEngine:
    """One local full-request execution at a time under an exact full grant.

    The engine retains its original guarded-context and resource checks.
    Its independent backend identity pin is not a claim that the backend
    mapped the weight-store pages. That loader binding requires separate
    native qualification. The caller retains ownership of the engine.
    """

    def __init__(self, session: OfflineRuntimeSession, engine: LocalInferenceEngine, *,
                 backend_digest: str) -> None:
        require(isinstance(session, OfflineRuntimeSession), "trusted runtime session required")
        require(isinstance(engine, LocalInferenceEngine), "canonical local engine required")
        self._backend_digest = identity(backend_digest, "backend digest")
        require(engine.model.model_digest == self._backend_digest, "backend identity mismatch")
        self._session = session
        self._engine = engine
        self._lock = asyncio.Lock()
        self._closed = False
        self._sequence = 0
        self._consumer = session.claim_consumer()

    @asynccontextmanager
    async def _own_until(self, deadline_ns: int):
        remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
        require(remaining > 0, "whole request expired while waiting for execution ownership")
        # Bound waiting itself, not only dispatch after a possibly stuck owner.
        # The timeout scope ends immediately after successful acquisition.
        acquired = False
        try:
            try:
                async with asyncio.timeout(remaining):
                    await self._lock.acquire()
                    acquired = True
            except TimeoutError as exc:
                raise RuntimePreflightError("whole request expired while waiting for execution ownership") from exc
            yield
        finally:
            if acquired:
                self._lock.release()

    async def revalidate_source(self, *, timeout_ms: int = 10000) -> dict:
        """Wait for idle ownership, then explicitly rescan the pinned source.

        timeout_ms bounds lock waiting, not synchronous filesystem hashing.
        The rescan is trusted operator maintenance, not an inference request.
        """
        timeout = integer(timeout_ms, 1, 86_400_000, "reinspection wait timeout")
        async with self._own_until(time.monotonic_ns() + timeout * 1_000_000):
            require(not self._closed and not self._session.status()["closed"],
                    "whole-request adapter is closed")
            return self._session.revalidate_source(consumer=self._consumer)

    async def generate(self, request: LocalInferenceRequest, *, max_input_tokens: int,
                       timeout_ms: int) -> WholeRequestOutcome:
        require(isinstance(request, LocalInferenceRequest), "canonical inference request required")
        require(not request.tools and request.tool_choice in ("none", "auto"),
                "whole-request adapter supports inference only, without tool authority")
        input_ceiling = integer(max_input_tokens, 1, 65536, "input allowance")
        timeout = integer(timeout_ms, 1, 86_400_000, "request timeout")
        demand = input_ceiling + request.max_output_tokens
        require(demand <= self._session.policy.maximum_tokens and
                demand <= self._session.policy.prefill_quantum,
                "whole request exceeds configured atomic token allowance")
        # Queue waiting consumes the caller's timeout, not a new budget.
        started = time.monotonic_ns()
        caller_deadline = started + timeout * 1_000_000
        async with self._own_until(caller_deadline):
            require(not self._closed and not self._session.status()["closed"], "whole-request adapter is closed")
            require(self._engine.model.model_digest == self._backend_digest, "backend identity changed")
            require(time.monotonic_ns() < caller_deadline, "whole request expired while waiting for execution ownership")
            self._sequence += 1
            operation = "whole-" + str(self._sequence)
            # This prefill-shaped scheduler request is a conservative reservation
            # of the complete input + output bound, not measured prefill work.
            observation = self._session.offer((IterationWork(
                operation, InferencePhase.PREFILL, demand),), consumer=self._consumer)
            grant = observation["admission"]
            receipt: dict[str, Any] = {
                "schema": "skeleton.offline.whole-request.v1",
                "operation": operation, "backend_digest": self._backend_digest,
                "request_digest": request.digest, "admission_digest": grant["admission_digest"],
                "source_digest": grant["source_digest"],
                "token_reservation": demand, "input_ceiling": input_ceiling,
                "output_ceiling": request.max_output_tokens,
                "backend_weight_binding": "not_assessed",
                "native_qualified": False, "release_qualified": False,
            }
            if grant["status"] != "candidate":
                return self._finish(receipt, "deferred")
            slices = self._session.consume(grant, consumer=self._consumer)
            if slices != ({"request_id": operation, "phase": "prefill", "tokens": demand},):
                return self._finish(receipt, "partial_grant_deferred")
            deadline_ns = min(
                self._session.execution_deadline(grant["expires_ns"], consumer=self._consumer),
                caller_deadline,
            )
            if time.monotonic_ns() >= deadline_ns:
                return self._finish(receipt, "expired_before_dispatch")
            try:
                result = await self._engine.generate(
                    request, deadline=deadline_ns / 1_000_000_000,
                    resource_max_input_tokens=input_ceiling,
                    resource_max_output_tokens=request.max_output_tokens,
                )
                require(isinstance(result, LocalInferenceResult) and
                        result.model_digest == self._backend_digest and
                        self._engine.model.model_digest == self._backend_digest,
                        "backend execution identity mismatch")
                require(result.input_tokens <= input_ceiling and
                        result.output_tokens <= request.max_output_tokens,
                        "backend exceeded reserved token limits")
                require(not result.tool_calls, "unexpected tool output")
            except BaseException:
                self._closed = True
                self._session.close()
                raise
            # Even a real result is not published if it exceeded the grant's
            # lifetime, was cancelled, or failed the canonical completion reason.
            if (self._closed or self._session.status()["closed"] or time.monotonic_ns() >= deadline_ns or
                    result.finish_reason not in ("completed", "length")):
                return self._finish(receipt, "terminal_without_output")
            receipt["usage"] = {"input_tokens": result.input_tokens,
                                "output_tokens": result.output_tokens,
                                "source": result.usage_source, "cached": result.cached}
            receipt["engine_receipt_digest"] = result.execution_receipt_digest
            return self._finish(receipt, "completed", result)

    @staticmethod
    def _finish(receipt: dict, status: str,
                result: LocalInferenceResult | None = None) -> WholeRequestOutcome:
        output_digest = None
        if result is not None:
            # Hash bounded UTF-8 output separately from the small receipt.
            # JSON ASCII escapes can otherwise expand a valid output.
            text_digest = sha256(result.text.encode("utf-8")).hexdigest() if result.text is not None else None
            structured_digest = None
            if result.structured_output is not None:
                structured = json.dumps(dict(result.structured_output), sort_keys=True,
                                        separators=(",", ":"), ensure_ascii=False,
                                        allow_nan=False).encode("utf-8")
                structured_digest = sha256(structured).hexdigest()
            output_digest = digest({
                "model_id": result.model_id, "model_digest": result.model_digest,
                "text_digest": text_digest, "structured_digest": structured_digest,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "finish_reason": result.finish_reason, "response_id": result.response_id,
                "usage_source": result.usage_source, "cached": result.cached,
                "execution_receipt_digest": result.execution_receipt_digest,
                "latency_ms": result.latency_ms,
            })
        body = {**receipt, "status": status, "output_digest": output_digest}
        return WholeRequestOutcome({**body, "receipt_digest": digest(body)}, result)

    def close(self) -> None:
        # A running engine operation still owns its original cancellation and
        # cleanup lifecycle. This adapter will refuse to publish its result.
        self._closed = True
        self._session.close()
