"""CPU-only native transformer backend for authenticated fair-stream results.

This is a real NativeLLMRuntime integration, not a tokenizer proxy or simulated
provider. Prompts are ephemeral and explicitly registered by the authenticated
application; the durable execution journal is the replay fence across crashes.
No prompt or key material is written into scheduler checkpoints or receipts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
import hmac
import os
import secrets
from threading import Event, RLock
from time import monotonic_ns
from typing import Mapping

from .fair_stream_result_vault import MAX_RESULT_BYTES
from .flgb_model_runtime import digest_json
from .fair_stream_session import DispatchPermit
from .fair_stream_queue import StreamRequest, WHOLE_REQUEST_SCHEMA
from .native_llm_runtime import GenerationResult, NativeLLMRuntime
from .runtime_contracts import GenerationConfig, ReplayReceipt, RuntimeUsage, RuntimeEvent
from .native_token_pressure import NativeTokenPressureGuard, _canonical_cpu_permit
from .native_prompt_budget import NativePromptBudget, PromptBudgetLedger

MAX_PROMPT_BYTES = 64 << 10
MAX_STAGED_PROMPTS = 256
MAX_PROMPT_IDENTITIES = 10_000  # separate bounded lifetime replay inventory
MAX_ID_BYTES = 128
MAX_PROMPT_STAGE_AGE_NS = 3_600_000_000_000
DEFAULT_PROMPT_STAGE_AGE_NS = 300_000_000_000


class NativeFairStreamDenied(RuntimeError):
    """No execution is authorized; an uncertain owner must not auto-retry."""


class NativeExecutionInterrupted(NativeFairStreamDenied):
    """Authenticated cooperative stop; never a signed result or retry grant."""


def _require_owner_process(owner_pid: int) -> None:
    """A fork inherits staged plaintext and Python locks, not execution rights.

    Reject before entering any inherited RLock: a parent thread holding that
    lock might not exist in the child, and a copied grant is not a new lease.
    """
    try:
        current = os.getpid()
    except BaseException as exc:
        raise NativeFairStreamDenied(
            "native prompt process identity unavailable"
        ) from exc
    if type(current) is not int or current != owner_pid:
        raise NativeFairStreamDenied(
            "forked native prompt authority requires reauthorization"
        )


def _id(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > MAX_ID_BYTES:
        raise NativeFairStreamDenied("invalid " + label)
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise NativeFairStreamDenied("invalid " + label + " Unicode") from exc
    if len(raw) > MAX_ID_BYTES or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise NativeFairStreamDenied("invalid " + label)
    return value


def _digest(value: object, label: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise NativeFairStreamDenied("invalid " + label)
    return value


def _cpu_runtime(runtime: NativeLLMRuntime) -> tuple[str, str]:
    if type(runtime) is not NativeLLMRuntime:
        raise NativeFairStreamDenied("canonical native transformer runtime required")
    # This adapter cannot certify GPU/M-chip execution or a mixed-device
    # fallback. An operator must separately qualify those paths.
    if (runtime.device_policy.requested != "cpu"
            or runtime.device.actual != "cpu"
            or runtime.device.resident
            or getattr(runtime.model, "device", None) != "cpu"
            or getattr(runtime.model, "resident", False)):
        raise NativeFairStreamDenied("unqualified native execution device")
    try:
        runtime.assert_model_unchanged()
        runtime.tokenizer.assert_unchanged()
    except Exception as exc:
        raise NativeFairStreamDenied("native model/tokenizer identity drift") from exc
    return _digest(runtime.model_digest, "model digest"), _digest(
        runtime.tokenizer.digest, "tokenizer digest",
    )


@dataclass(frozen=True, slots=True)
class PinnedNativePrompt:
    """Immutable prompt authorization; plaintext remains only in app RAM."""

    session_id: str
    request_id: str
    tenant_id: str
    prompt: str
    prompt_digest: str
    model_digest: str
    tokenizer_digest: str
    max_output_tokens: int

    def __post_init__(self) -> None:
        _id(self.session_id, "session")
        _id(self.request_id, "request")
        _id(self.tenant_id, "tenant")
        _digest(self.prompt_digest, "prompt digest")
        _digest(self.model_digest, "model digest")
        _digest(self.tokenizer_digest, "tokenizer digest")
        if type(self.prompt) is not str:
            raise NativeFairStreamDenied("text prompt required")
        if not 1 <= len(self.prompt) <= MAX_PROMPT_BYTES:
            raise NativeFairStreamDenied("prompt byte budget exceeded")
        try:
            raw = self.prompt.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise NativeFairStreamDenied("invalid prompt Unicode") from exc
        if not raw or len(raw) > MAX_PROMPT_BYTES:
            raise NativeFairStreamDenied("prompt byte budget exceeded")
        if not hmac.compare_digest(sha256(raw).hexdigest(), self.prompt_digest):
            raise NativeFairStreamDenied("prompt identity mismatch")
        if type(self.max_output_tokens) is not int or self.max_output_tokens < 1:
            raise NativeFairStreamDenied("positive output token cap required")


def pin_native_prompt(
    runtime: NativeLLMRuntime, *, session_id: str, request_id: str,
    tenant_id: str, prompt: str, max_output_tokens: int,
) -> PinnedNativePrompt:
    """Admit a prompt against the SAME CPU model/tokenizer used at execution."""
    _id(session_id, "session")
    _id(request_id, "request")
    _id(tenant_id, "tenant")
    if type(prompt) is not str:
        raise NativeFairStreamDenied("text prompt required")
    if not 1 <= len(prompt) <= MAX_PROMPT_BYTES:
        raise NativeFairStreamDenied("prompt byte budget exceeded")
    try:
        raw = prompt.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise NativeFairStreamDenied("invalid prompt Unicode") from exc
    if not raw or len(raw) > MAX_PROMPT_BYTES:
        raise NativeFairStreamDenied("prompt byte budget exceeded")
    model_digest, tokenizer_digest = _cpu_runtime(runtime)
    if (type(max_output_tokens) is not int
            or not 1 <= max_output_tokens <= runtime.limits.max_new_tokens):
        raise NativeFairStreamDenied("output exceeds native runtime limit")
    try:
        sequence = runtime.encode(prompt)
        if runtime.tokenizer.decode_ids(sequence.token_ids) != prompt:
            raise NativeFairStreamDenied("native tokenizer cannot roundtrip prompt")
    except NativeFairStreamDenied:
        raise
    except Exception as exc:
        raise NativeFairStreamDenied("native tokenizer admission failed") from exc
    if (len(sequence.token_ids) + max_output_tokens > runtime.limits.max_context
            or runtime.estimate_kv_bytes(
                len(sequence.token_ids) + max_output_tokens,
            ) > runtime.limits.max_kv_bytes):
        raise NativeFairStreamDenied("native context or KV budget exceeded")
    return PinnedNativePrompt(
        session_id=session_id, request_id=request_id, tenant_id=tenant_id,
        prompt=prompt, prompt_digest=sha256(raw).hexdigest(),
        model_digest=model_digest, tokenizer_digest=tokenizer_digest,
        max_output_tokens=max_output_tokens,
    )


class NativePromptRegistry:
    """Bounded app-RAM one-use prompt grants; no implicit restart recovery.

    Each request ID may be registered only once for the lifetime of this
    registry, including after generation fails. The external durable journal
    remains authoritative across process restarts. Never recreate a RUNNING
    lease on startup or use this registry as a replacement for durable CAS.
    """

    def __init__(
        self, *, session_id: str, budget: NativePromptBudget | None = None,
        max_stage_age_ns: int = DEFAULT_PROMPT_STAGE_AGE_NS,
    ) -> None:
        self.session_id = _id(session_id, "session")
        if (type(max_stage_age_ns) is not int
                or not 1 <= max_stage_age_ns <= MAX_PROMPT_STAGE_AGE_NS):
            raise NativeFairStreamDenied("invalid prompt staging lifetime")
        self._owner_pid = os.getpid()
        self._binding_key = secrets.token_bytes(32)
        if type(self._binding_key) is not bytes or len(self._binding_key) != 32:
            raise NativeFairStreamDenied("prompt binding key generation failed")
        self._lock = RLock()
        self._staged: dict[str, PinnedNativePrompt] = {}
        self._staged_at: dict[str, int] = {}
        self._used: set[str] = set()
        self._budget = PromptBudgetLedger(NativePromptBudget() if budget is None else budget)
        self._max_stage_age_ns = max_stage_age_ns
        self._last_clock_ns = -1
        self._clock_invalidated = False

    def _require_owner_process(self) -> None:
        _require_owner_process(self._owner_pid)

    def _clock_locked(self) -> int:
        """Never grant on unknown, nonmonotonic or malformed local time."""
        if self._clock_invalidated:
            raise NativeFairStreamDenied("prompt monotonic clock authority invalidated; reopen required")
        try:
            now = monotonic_ns()
        except BaseException as exc:
            self._clock_invalidated = True
            raise NativeFairStreamDenied("prompt monotonic clock unavailable") from exc
        if type(now) is not int or now < 0 or now < self._last_clock_ns:
            self._clock_invalidated = True
            raise NativeFairStreamDenied("prompt monotonic clock regressed")
        self._last_clock_ns = now
        return now

    def _expire_locked(self, now: int) -> None:
        """Burn stale identities before admitting any new prompt RAM."""
        if (set(self._staged) != set(self._staged_at)
                or any(type(ts) is not int or ts < 0 or ts > now
                       for ts in self._staged_at.values())):
            raise NativeFairStreamDenied("prompt staging timestamp invariant failed")
        if (len(self._staged) > MAX_STAGED_PROMPTS
                or len(self._staged) + len(self._used) > MAX_PROMPT_IDENTITIES
                or not self._used.isdisjoint(self._staged)
                or any(type(pinned) is not PinnedNativePrompt
                       or pinned.request_id != rid or pinned.session_id != self.session_id
                       for rid, pinned in self._staged.items())
                or self._budget.snapshot()["staged_grants"] != len(self._staged)):
            raise NativeFairStreamDenied("prompt registry custody invariant failed")
        # A bounded registry guarantees this sweep is never unbounded.
        expired = [request_id for request_id, staged_at in self._staged_at.items()
                   if now - staged_at >= self._max_stage_age_ns]
        for request_id in expired:
            pinned = self._staged[request_id]
            self._budget.release(pinned.tenant_id, len(pinned.prompt.encode("utf-8")))
            del self._staged[request_id]
            del self._staged_at[request_id]
            self._used.add(request_id)

    def stage(self, pinned: PinnedNativePrompt) -> None:
        _require_owner_process(self._owner_pid)
        if type(pinned) is not PinnedNativePrompt:
            raise NativeFairStreamDenied("canonical pinned prompt required")
        if pinned.session_id != self.session_id:
            raise NativeFairStreamDenied("prompt session mismatch")
        with self._lock:
            now = self._clock_locked()
            self._expire_locked(now)
            if pinned.request_id in self._used or pinned.request_id in self._staged:
                raise NativeFairStreamDenied("duplicate or consumed request identity")
            if len(self._staged) >= MAX_STAGED_PROMPTS:
                raise NativeFairStreamDenied("concurrent prompt staging capacity exhausted")
            if len(self._staged) + len(self._used) >= MAX_PROMPT_IDENTITIES:
                raise NativeFairStreamDenied("prompt identity capacity exhausted")
            # Charge real UTF-8 bytes, not characters or token estimates.
            # Reservation precedes publication: a denied grant never becomes
            # visible to a concurrent claimant.
            self._budget.reserve(pinned.tenant_id, len(pinned.prompt.encode("utf-8")))
            self._staged[pinned.request_id] = pinned
            self._staged_at[pinned.request_id] = now

    def _commitment(self, pinned: PinnedNativePrompt, request: Mapping[str, object]) -> str:
        # The process-private key is never serialized; the commitment cannot
        # be regenerated on restart, even from the same plaintext prompt.
        fields = {
            "schema": "skeleton.ai.native-prompt-authorization.v1",
            "session_id": pinned.session_id,
            "request_id": pinned.request_id,
            "tenant_id": pinned.tenant_id,
            "prompt_digest": pinned.prompt_digest,
            "model_digest": pinned.model_digest,
            "tokenizer_digest": pinned.tokenizer_digest,
            "max_output_tokens": pinned.max_output_tokens,
            "remaining_tokens": request.get("remaining_tokens"),
            "bytes_per_token": request.get("bytes_per_token"),
            "phase": request.get("phase"),
            "priority": request.get("priority"),
        }
        return hmac.new(self._binding_key, digest_json(fields).encode("ascii"), sha256).hexdigest()

    def _verified_pinned(self, request: Mapping[str, object], *, bound: bool) -> PinnedNativePrompt:
        rid = _id(request.get("request_id"), "request")
        tenant = _id(request.get("tenant_id"), "tenant")
        tokens = request.get("remaining_tokens")
        pinned = self._staged.get(rid)
        if (pinned is None or pinned.tenant_id != tenant or type(tokens) is not int
                or not 1 <= tokens <= pinned.max_output_tokens):
            raise NativeFairStreamDenied("queued prompt authorization unavailable; cancel explicitly")
        if bound:
            commitment = _digest(request.get("authorization_digest"), "request authorization")
            if not hmac.compare_digest(commitment, self._commitment(pinned, request)):
                raise NativeFairStreamDenied("queued prompt authorization commitment mismatch")
        return pinned

    def bind_request(self, request: StreamRequest) -> StreamRequest:
        """Bind the exact staged grant before durable publication."""
        _require_owner_process(self._owner_pid)
        if type(request) is not StreamRequest or request.authorization_digest is not None:
            raise NativeFairStreamDenied("unbound canonical request required")
        row = {
            "request_id": request.request_id, "tenant_id": request.tenant_id,
            "remaining_tokens": request.remaining_tokens, "bytes_per_token": request.bytes_per_token,
            "phase": request.phase.value, "priority": request.priority,
        }
        with self._lock:
            self._expire_locked(self._clock_locked())
            pinned = self._verified_pinned(row, bound=False)
            return replace(request, authorization_digest=self._commitment(pinned, row))

    def claim(self, request_id: str, tenant_id: str, *,
              authorized_request: Mapping[str, object] | None = None) -> PinnedNativePrompt:
        """Consume before invoking a potentially side-effecting model."""
        _require_owner_process(self._owner_pid)
        with self._lock:
            self._expire_locked(self._clock_locked())
            pinned = self._staged.get(_id(request_id, "request"))
            if pinned is None or pinned.tenant_id != _id(tenant_id, "tenant"):
                raise NativeFairStreamDenied("missing authorized prompt")
            if authorized_request is not None:
                if self._verified_pinned(authorized_request, bound=True) is not pinned:
                    raise NativeFairStreamDenied("native request authorization identity mismatch")
            self._budget.release(pinned.tenant_id, len(pinned.prompt.encode("utf-8")))
            self._used.add(request_id)
            del self._staged[request_id]
            del self._staged_at[request_id]
            return pinned

    def verify_queued(self, requests: list[dict[str, object]]) -> None:
        """Read-only authorization check before a durable plan can mint a lease.

        A lost, expired or mismatched prompt is not permission to reconstruct
        plaintext. The owning tenant may explicitly cancel that queued item.
        """
        _require_owner_process(self._owner_pid)
        if type(requests) is not list or len(requests) > MAX_STAGED_PROMPTS:
            raise NativeFairStreamDenied("native queued prompt capacity exceeded")
        with self._lock:
            self._expire_locked(self._clock_locked())
            seen: set[str] = set()
            for request in requests:
                if type(request) is not dict:
                    raise NativeFairStreamDenied("invalid native queued request")
                rid = _id(request.get("request_id"), "request")
                if rid in seen:
                    raise NativeFairStreamDenied("duplicate queued prompt identity")
                seen.add(rid)
                self._verified_pinned(request, bound=True)

    def revoke(self, request_id: str) -> None:
        """Burn a pending grant without authorizing an execution."""
        _require_owner_process(self._owner_pid)
        with self._lock:
            self._expire_locked(self._clock_locked())
            _id(request_id, "request")
            pinned = self._staged.get(request_id)
            if (pinned is None and request_id not in self._used
                    and len(self._staged) + len(self._used) >= MAX_PROMPT_IDENTITIES):
                raise NativeFairStreamDenied("prompt identity capacity exhausted")
            if pinned is not None:
                self._budget.release(pinned.tenant_id, len(pinned.prompt.encode("utf-8")))
                del self._staged[request_id]
                del self._staged_at[request_id]
            self._used.add(request_id)

    def discard_cancelled(self, request_id: str) -> None:
        """Release an explicitly cancelled grant even if the clock failed.

        Invoke only on an authenticated cancellation or failed admission;
        cleanup may precede final queue retirement to make it recoverable.
        Unknown identities need not grow the lifetime set beyond its cap:
        admission is already exhausted until the registry is retired.
        """
        _require_owner_process(self._owner_pid)
        rid = _id(request_id, "request")
        with self._lock:
            pinned = self._staged.get(rid)
            if pinned is not None:
                self._budget.release(pinned.tenant_id, len(pinned.prompt.encode("utf-8")))
                del self._staged[rid]
                del self._staged_at[rid]
                self._used.add(rid)
            elif len(self._staged) + len(self._used) < MAX_PROMPT_IDENTITIES:
                self._used.add(rid)

    def status(self) -> dict[str, int | str]:
        _require_owner_process(self._owner_pid)
        with self._lock:
            self._expire_locked(self._clock_locked())
            return {
                "schema": "skeleton.ai.native-fair-stream-prompt-status.v1",
                "staged": len(self._staged),
                "consumed_or_revoked": len(self._used),
                "staged_prompt_bytes": self._budget.snapshot()["staged_bytes"],
            }

    def budget_status(self) -> dict[str, int | str]:
        """Payload-free operator telemetry; never expose prompts or tenant IDs."""
        _require_owner_process(self._owner_pid)
        with self._lock:
            self._expire_locked(self._clock_locked())
            return self._budget.snapshot()


class NativeFairStreamBackend:
    """NativeLLMRuntime -> encrypted result vault's OfflineInferenceBackend.

    The application must independently authenticate tenants before staging
    prompts. Fair-stream session and journal authorize actual lease execution.
    A request can be executed only once in this process, and any failure after
    claim is outcome-uncertain to the outer durable execution owner.
    """

    def __init__(
        self, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
        *, pressure_guard: NativeTokenPressureGuard | None = None,
    ) -> None:
        model, tokenizer = _cpu_runtime(runtime)
        if type(registry) is not NativePromptRegistry:
            raise NativeFairStreamDenied("canonical prompt registry required")
        self.runtime = runtime
        self.registry = registry
        self._owner_pid = os.getpid()
        if pressure_guard is not None and type(pressure_guard) is not NativeTokenPressureGuard:
            raise NativeFairStreamDenied("canonical native pressure guard required")
        self._pressure_guard = pressure_guard
        self.model_digest = model
        self.tokenizer_digest = tokenizer
        self._lock = RLock()
        self._interrupt_lock = RLock()
        self._active_interrupt: tuple[str, str, Event] | None = None

    def request_interrupt(self, *, tenant_id: str, request_id: str) -> bool:
        """Signal only the exact active authenticated request; never await inference."""
        _require_owner_process(self._owner_pid)
        tenant, request = _id(tenant_id, "tenant"), _id(request_id, "request")
        with self._interrupt_lock:
            active = self._active_interrupt
            if active is None or active[:2] != (tenant, request):
                return False
            active[2].set()
            return True

    @contextmanager
    def _interrupt_scope(self, tenant: str, request: str):
        signal = Event()
        with self._interrupt_lock:
            if self._active_interrupt is not None:
                raise NativeFairStreamDenied("native interrupt scope already active")
            self._active_interrupt = (tenant, request, signal)
        try:
            yield signal
        finally:
            with self._interrupt_lock:
                if self._active_interrupt is not None and self._active_interrupt[2] is signal:
                    self._active_interrupt = None

    def _seal_interrupt_scope(self, signal: Event) -> None:
        """Linearize a completed generation against a concurrent stop."""
        with self._interrupt_lock:
            active = self._active_interrupt
            if active is None or active[2] is not signal:
                raise NativeFairStreamDenied("native interrupt scope changed")
            if signal.is_set():
                raise NativeExecutionInterrupted("authenticated native interruption requested")
            self._active_interrupt = None

    def reauthorize_retired_lease(self, permit: DispatchPermit) -> None:
        """Only the trusted durable retirement owner may call this seam."""
        _require_owner_process(self._owner_pid)
        self.registry._require_owner_process()
        with self._lock:
            with self._interrupt_lock:
                if self._active_interrupt is not None:
                    raise NativeFairStreamDenied("cannot reauthorize active native execution")
            if self._pressure_guard is not None:
                self._pressure_guard.reauthorize_retired_lease(permit)

    def _pending(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> str:
        if not _canonical_cpu_permit(permit):
            raise NativeFairStreamDenied("CPU-only canonical permit required")
        if (type(state) is not dict
                or state.get("session_id") != self.registry.session_id
                or type(state.get("generation")) is not int
                or state.get("generation") != permit.generation
                or state.get("checkpoint_digest") != permit.checkpoint_digest):
            raise NativeFairStreamDenied("session generation mismatch")
        checkpoint = state.get("checkpoint")
        if type(checkpoint) is not dict:
            raise NativeFairStreamDenied("missing durable checkpoint")
        pending = checkpoint.get("pending")
        requests = checkpoint.get("requests")
        if (type(pending) is not list or len(pending) != 1
                or type(pending[0]) is not dict
                or type(requests) is not list):
            raise NativeFairStreamDenied("invalid pending lease cardinality")
        lease = pending[0]
        if (type(lease.get("lease_id")) is not str
                or type(lease.get("request_id")) is not str
                or type(lease.get("tenant_id")) is not str
                or type(lease.get("tokens")) is not int
                or type(lease.get("bytes_reserved")) is not int
                or lease.get("lease_id") != permit.lease_id
                or lease.get("request_id") != permit.request_id
                or lease.get("tokens") != permit.tokens
                or lease.get("bytes_reserved") != permit.bytes_reserved):
            raise NativeFairStreamDenied("pending lease identity mismatch")
        matching = [item for item in requests
                    if type(item) is dict and item.get("request_id") == permit.request_id]
        if len(matching) != 1:
            raise NativeFairStreamDenied("missing canonical stream request")
        request = matching[0]
        if (
            type(request.get("tenant_id")) is not str
            or request["tenant_id"] != lease["tenant_id"]
        ):
            raise NativeFairStreamDenied("lease and request tenant mismatch")
        # One-use native prompts cannot resume a generic partial lease.
        # The app must admit a whole request before burning the RAM grant.
        if (type(request.get("remaining_tokens")) is not int
                or request["remaining_tokens"] != permit.tokens):
            raise NativeFairStreamDenied("native whole-request lease required")
        bytes_per_token = request.get("bytes_per_token")
        if (type(bytes_per_token) is not int or bytes_per_token <= 0
                or type(permit.tokens) is not int or permit.tokens <= 0
                or permit.tokens * bytes_per_token != permit.bytes_reserved):
            raise NativeFairStreamDenied("lease memory accounting mismatch")
        return _id(request.get("tenant_id"), "tenant")

    def generate(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> tuple[int, bytes]:
        _require_owner_process(self._owner_pid)
        self.registry._require_owner_process()
        with self._lock:
            tenant = self._pending(permit, state)
            model, tokenizer = _cpu_runtime(self.runtime)
            if (not hmac.compare_digest(model, self.model_digest)
                    or not hmac.compare_digest(tokenizer, self.tokenizer_digest)):
                raise NativeFairStreamDenied("pinned native runtime changed")
            # Claim is intentionally irreversible, even on a preflight failure.
            checkpoint = state["checkpoint"]
            authorized_request = None
            if checkpoint.get("schema") == WHOLE_REQUEST_SCHEMA:
                authorized_request = next(
                    item for item in checkpoint["requests"]
                    if item["request_id"] == permit.request_id
                )
            pinned = self.registry.claim(
                permit.request_id, tenant, authorized_request=authorized_request,
            )
            if (pinned.max_output_tokens < permit.tokens
                    or not hmac.compare_digest(pinned.model_digest, model)
                    or not hmac.compare_digest(pinned.tokenizer_digest, tokenizer)):
                raise NativeFairStreamDenied("prompt/model/output grant mismatch")
            with self._interrupt_scope(tenant, permit.request_id) as signal:
                try:
                    sequence = self.runtime.encode(pinned.prompt)
                    if (sha256(pinned.prompt.encode("utf-8")).hexdigest()
                            != pinned.prompt_digest
                            or self.runtime.tokenizer.decode_ids(sequence.token_ids)
                            != pinned.prompt):
                        raise NativeFairStreamDenied("tokenizer roundtrip or prompt drift")
                    if (len(sequence.token_ids) + permit.tokens > self.runtime.limits.max_context
                            or self.runtime.estimate_kv_bytes(
                                len(sequence.token_ids) + permit.tokens,
                            ) > self.runtime.limits.max_kv_bytes):
                        raise NativeFairStreamDenied("native context/KV pressure limit")
                    config = GenerationConfig(max_new_tokens=permit.tokens)
                    guard = self._pressure_guard
                    pressure_interrupt = guard.start(permit) if guard is not None else None

                    def interrupt() -> None:
                        if signal.is_set():
                            raise NativeExecutionInterrupted("authenticated native interruption requested")
                        if pressure_interrupt is not None:
                            pressure_interrupt()
                        if signal.is_set():
                            raise NativeExecutionInterrupted("authenticated native interruption requested")

                    succeeded = False
                    try:
                        result = self.runtime.generate_sequence(
                            sequence, config, interrupt=interrupt,
                        )
                        _cpu_runtime(self.runtime)
                        # A native model returning an object is NOT a completion:
                        # validate its exact identity, token accounting, output
                        # encoding and result capacity while the guard is active.
                        if type(result) is not GenerationResult:
                            raise NativeFairStreamDenied("untrusted native generation result")
                        receipt = result.replay_receipt
                        if (type(receipt) is not ReplayReceipt
                                or type(result.usage) is not RuntimeUsage
                                or type(result.text) is not str
                                or type(result.finish_reason) is not str
                                or type(result.generated_ids) is not tuple
                                or any(type(token_id) is not int
                                       or not 0 <= token_id < self.runtime.tokenizer.vocab_size
                                       for token_id in result.generated_ids)
                                or type(result.usage.generated_tokens) is not int
                                or result.usage.generated_tokens != len(result.generated_ids)
                                or result.usage.generated_tokens > permit.tokens
                                or type(result.usage.prompt_tokens) is not int
                                or result.usage.prompt_tokens != len(sequence.token_ids)
                                or type(result.usage.total_tokens) is not int
                                or result.usage.model_bytes != self.runtime.model_bytes
                                or type(result.usage.kv_peak_bytes) is not int
                                or not 0 <= result.usage.kv_peak_bytes <= self.runtime.limits.max_kv_bytes
                                or result.usage.total_tokens != (
                                    len(sequence.token_ids) + len(result.generated_ids)
                                )
                                or receipt.model_digest != model
                                or receipt.tokenizer_digest != tokenizer
                                or receipt.architecture_digest != self.runtime.architecture.digest
                                or receipt.device_digest != self.runtime.device.digest
                                or receipt.config_digest != self.runtime._config_digest(config)
                                or receipt.request_digest != self.runtime._request_digest(
                                    sequence, config,
                                )
                                or type(receipt.seed) is not int
                                or receipt.seed != config.seed
                                or receipt.output_digest != digest_json({
                                    "generated_ids": list(result.generated_ids),
                                    "text": result.text,
                                    "finish_reason": result.finish_reason,
                                })
                                or type(result.prompt_sequence) is not type(sequence)
                                or result.prompt_sequence != sequence):
                            raise NativeFairStreamDenied("native output attestation mismatch")
                        # This adapter supplies a fixed positive-length policy
                        # without stop IDs or stop strings. A shorter trajectory
                        # is not an authentic completion under that policy.
                        if (config.stop_token_ids or config.stop_strings
                                or result.finish_reason != "length"
                                or len(result.generated_ids) != config.max_new_tokens
                                or type(result.generated_tokens) is not tuple
                                or result.generated_tokens != tuple(
                                    self.runtime.tokenizer.token_text(token_id)
                                    for token_id in result.generated_ids
                                )
                                or result.text != self.runtime.tokenizer.decode_ids(result.generated_ids)
                                or type(result.events) is not tuple
                                or not result.events
                                or len(result.events) > config.max_new_tokens + 4
                                or any(type(event) is not RuntimeEvent for event in result.events)
                                or tuple(event.sequence for event in result.events)
                                != tuple(range(len(result.events)))
                                or result.events[-1].kind != "completed"
                                or result.events[-1].detail_digest != receipt.digest
                                or tuple(event.token_id for event in result.events if event.kind == "token")
                                != result.generated_ids):
                            raise NativeFairStreamDenied("native output trajectory mismatch")
                        _digest(result.checkpoint_digest, "native checkpoint digest")
                        try:
                            output = result.text.encode("utf-8", errors="strict")
                        except UnicodeEncodeError as exc:
                            raise NativeFairStreamDenied("invalid native output Unicode") from exc
                        if len(output) > MAX_RESULT_BYTES:
                            raise NativeFairStreamDenied("native output exceeds sealed vault limit")
                        # A final independent OS sample fences thermal/memory
                        # pressure that changed after the last model callback.
                        # A postflight hold is outcome-uncertain: no result escapes
                        # to the encrypted vault or durable success journal.
                        interrupt()
                        self._seal_interrupt_scope(signal)
                        succeeded = True
                        return result.usage.generated_tokens, output
                    finally:
                        if guard is not None:
                            guard.finish(success=succeeded)
                except NativeFairStreamDenied:
                    raise
                except Exception as exc:
                    raise NativeFairStreamDenied("native inference failed; no retry") from exc
