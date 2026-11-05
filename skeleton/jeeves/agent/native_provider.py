"""Native GGUF bridge for the existing Jeeves agent/provider contract.

The only model execution path is the canonical, trusted, installed local model
through SupervisedAI/ExecutionSpine. It must be constructed from the existing
activate_checked installation path. No hosted fallback, implicit retries,
model-originated tool execution, auto-approval, or success fabrication.
"""
from __future__ import annotations

from hashlib import sha256
import json
import threading
import time
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.turn_bridge import TurnBridge
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Conflict

from .native_prompt_boundary import prepare_native_prompt
from .native_receipt_boundary import receive_committed_turn
from .native_schema_boundary import verify_structured_native_output
from .provider import ModelCapabilities, ProviderError, ProviderRouter, RetryPolicy
from .types import ModelRequest, ModelResponse


class NativeJeevesProvider:
    """One host-checked native generation per uniquely bound Jeeves model call.

    Request identity maps to a durable single-turn session, preventing a
    committed response for one input from being mistaken for another. A failed
    or uncertain native call is not retried; the existing spine retains pending
    ownership for explicit operator reconciliation. The caller must configure
    its ProviderRouter with max_attempts=1 and no cross-request cache.
    """

    name = "jeeves_native"

    def __init__(self, worker: Any, *, maximum_attempts: int = 8192) -> None:
        # Once this bounded process-local uncertainty fence is full, admit
        # replay reads but hold new generation until a cold process restart.
        # The canonical SQLite spine preserves durable pending/commit fencing.
        if type(maximum_attempts) is not int or not 1 <= maximum_attempts <= 65536:
            raise ProviderError("bounded native attempt-fence capacity required")
        self._maximum_attempts = maximum_attempts
        self._worker = worker
        self._identity = ActiveModel.from_supervisor(worker)
        self._bridge = TurnBridge(worker)
        limits = worker.spine.limits
        if limits.max_output_tokens >= limits.context_tokens:
            raise ProviderError("invalid native model limits")
        self.model = "gguf_" + self._identity.model_sha256[:24]
        self.capabilities = ModelCapabilities(
            system_prompt=True,
            tools=False,
            structured_output=False,
            streaming=False,
            max_context_tokens=limits.context_tokens,
            max_output_tokens=limits.max_output_tokens,
        )
        # Per-process serialization complements the native process/session
        # locks and avoids races around durable session allocation.
        self._lock = threading.RLock()
        self._attempted: set[str] = set()

    @property
    def identity(self) -> ActiveModel:
        return self._identity

    def available(self) -> bool:
        try:
            return ActiveModel.from_supervisor(self._worker) == self._identity
        except (ValueError, AttributeError):
            return False

    def _keys(self, request: ModelRequest) -> tuple[str, str]:
        raw = json.dumps(
            {"tenant": self._identity.tenant,
             "subject": self._identity.subject,
             "model": self._identity.model_sha256,
             "tokenizer": self._identity.tokenizer_sha256,
             "request_id": request.request_id},
            sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
        digest = sha256(raw).hexdigest()
        return "js_" + digest[:40], "jr_" + digest[40:]

    def _ensure_session(self, session: str) -> None:
        try:
            self._worker.spine.create(session)
        except Conflict:
            # The owner-bound history read independently proves that the
            # existing session belongs to this exact tenant/model principal.
            self._worker.spine.history(session)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise ProviderError("Jeeves ModelRequest required")
        if not self.available():
            raise ProviderError("active native model principal has changed")
        limits = self._worker.spine.limits
        if request.max_tokens < limits.max_output_tokens:
            raise ProviderError("Jeeves budget smaller than configured native generation ceiling")
        # The native backend requires >0 sampler temperature. Host-defined
        # epsilon preserves the deterministic intent of temperature=0 without
        # claiming a special greedy decoding mode absent from backend proof.
        temperature = request.temperature if request.temperature > 0 else 0.000000001
        prompt = prepare_native_prompt(
            request, maximum_bytes=limits.input_bytes,
        )
        session, native_request_id = self._keys(request)
        started = time.monotonic()
        with self._lock:
            # The initial availability check happened before prompt encoding.
            # Recheck identity inside this provider's serialization fence
            # before opening SQLite state or attempting any native generation.
            if not self.available():
                raise ProviderError("active native principal changed before admission")
            # A process whose finite attempt fence is exhausted may still
            # inspect an existing committed SQLite result. It must NOT create
            # a new durable session merely to deny another generation.
            # This keeps quota refusal a read-only, fail-closed operation.
            full = (native_request_id not in self._attempted
                    and len(self._attempted) >= self._maximum_attempts)
            if full:
                try:
                    saved = self._worker.spine.replay(
                        session, native_request_id, prompt.text,
                        seed=0, temperature=temperature,
                    )
                except Conflict:
                    # Unknown session or conflicting request identity does
                    # not authorize the creation of any new durable state.
                    saved = None
                if saved is None:
                    raise ProviderError(
                        "native process attempt ledger at safe capacity"
                    )
            else:
                self._ensure_session(session)
                # Read-only replay first. Nothing may rerun an uncertain model
                # effect merely because Jeeves restarted or was called twice.
                saved = self._worker.spine.replay(
                    session, native_request_id, prompt.text,
                    seed=0, temperature=temperature,
                )
            if saved is not None:
                result = saved
            else:
                if native_request_id in self._attempted:
                    raise ProviderError("uncertain native request requires explicit custody reconciliation")
                if len(self._attempted) >= self._maximum_attempts:
                    # Never evict an uncertain operation merely to free RAM.
                    # A clean provider restart may re-admit new identities;
                    # SQLite remains the authority for old committed/pending work.
                    raise ProviderError("native process attempt ledger at safe capacity")
                # This in-process fence prevents a repeated call after an
                # exception. The canonical SQLite pending-state fence also
                # survives a process crash and prevents a duplicate inference.
                self._attempted.add(native_request_id)
                try:
                    generated = self._bridge.turn(
                        session, native_request_id, prompt.text,
                        seed=0, temperature=temperature,
                    )
                except ContractViolation as exc:
                    # Keep public failures precise without disclosing private
                    # native source details or retrying an uncertain effect.
                    if not self.available():
                        raise ProviderError(
                            "active native principal changed during generation"
                        ) from exc
                    raise ProviderError(
                        "native generation did not meet committed source contract"
                    ) from exc
                # The worker's returned dictionary alone is not proof that
                # SQLite committed. Independently read the authoritative
                # committed response and compare the exact original bytes.
                committed = self._worker.spine.replay(
                    session, native_request_id, prompt.text,
                    seed=0, temperature=temperature,
                )
                if committed is None:
                    raise ProviderError("native response lacks a durable committed replay")
                if (committed.get("text") != generated.get("text")
                    or committed.get("output_sha256") != generated.get("output_sha256")):
                    raise ProviderError("native response differs from durable committed bytes")
                result = dict(committed)
                result["replayed"] = False
            # Do not disclose a committed result as belonging to an active
            # principal if source/model identity changed during generation.
            # The durable SQLite receipt remains available for reconciliation.
            if not self.available():
                raise ProviderError("active native principal changed during generation")
        verified = receive_committed_turn(
            result, active=self._identity,
            session_id=session, native_request_id=native_request_id,
            maximum_output_tokens=request.max_tokens,
        )
        output = verify_structured_native_output(
            verified.text, request.response_schema,
            maximum_bytes=limits.response_bytes,
        )
        return ModelResponse(
            request_id=request.request_id,
            provider=self.name,
            model=self.model,
            content=output,
            prompt_tokens=verified.prompt_tokens,
            completion_tokens=verified.generated_tokens,
            finish_reason=verified.finish_reason,
            cached=verified.replayed,
            latency_ms=max(0.0, (time.monotonic() - started) * 1000.0),
            metadata={
                "native_output_sha256": verified.output_sha256,
                "native_model_sha256": verified.model_sha256,
                "native_tokenizer_sha256": verified.tokenizer_sha256,
                "native_session": session,
                "native_request_id": native_request_id,
                "prompt_envelope_sha256": prompt.sha256,
                "authoritative_commit": True,
                "device_qualified": False,
                "release_certified": False,
            },
        )


def native_provider_router(
    worker: Any,
    *,
    provider: NativeJeevesProvider | None = None,
) -> ProviderRouter:
    """One canonical source-checked provider with no retries or cache.

    Reusing the exact provider instance preserves its in-process uncertain
    inference fence and the immutable principal binding. The SQLite spine
    remains the durable cross-process replay authority.
    """
    native = provider if provider is not None else NativeJeevesProvider(worker)
    if (type(native) is not NativeJeevesProvider
            or native._worker is not worker
            or not native.available()):
        raise ProviderError("native provider must belong to the active worker")
    return ProviderRouter(
        (native,),
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0),
        cache_ttl_seconds=None,
    )


__all__ = ["NativeJeevesProvider", "native_provider_router"]
