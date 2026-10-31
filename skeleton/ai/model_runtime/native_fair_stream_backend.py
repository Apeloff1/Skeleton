"""CPU-only native transformer backend for authenticated fair-stream results.

This is a real NativeLLMRuntime integration, not a tokenizer proxy or simulated
provider. Prompts are ephemeral and explicitly registered by the authenticated
application; the durable execution journal is the replay fence across crashes.
No prompt or key material is written into scheduler checkpoints or receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
from threading import RLock
from typing import Mapping

from .fair_stream_result_vault import MAX_RESULT_BYTES
from .fair_stream_session import DispatchPermit
from .native_llm_runtime import NativeLLMRuntime
from .runtime_contracts import GenerationConfig, GenerationResult

MAX_PROMPT_BYTES = 64 << 10
MAX_STAGED_PROMPTS = 256
MAX_ID_BYTES = 128


class NativeFairStreamDenied(RuntimeError):
    """No execution is authorized; an uncertain owner must not auto-retry."""


def _id(value: object, label: str) -> str:
    if (type(value) is not str or not value
            or len(value.encode("utf-8")) > MAX_ID_BYTES
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
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
    model_digest, tokenizer_digest = _cpu_runtime(runtime)
    if type(prompt) is not str:
        raise NativeFairStreamDenied("text prompt required")
    try:
        raw = prompt.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise NativeFairStreamDenied("invalid prompt Unicode") from exc
    if not raw or len(raw) > MAX_PROMPT_BYTES:
        raise NativeFairStreamDenied("prompt byte budget exceeded")
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

    def __init__(self, *, session_id: str) -> None:
        self.session_id = _id(session_id, "session")
        self._lock = RLock()
        self._staged: dict[str, PinnedNativePrompt] = {}
        self._used: set[str] = set()

    def stage(self, pinned: PinnedNativePrompt) -> None:
        if type(pinned) is not PinnedNativePrompt:
            raise NativeFairStreamDenied("canonical pinned prompt required")
        if pinned.session_id != self.session_id:
            raise NativeFairStreamDenied("prompt session mismatch")
        with self._lock:
            if pinned.request_id in self._used or pinned.request_id in self._staged:
                raise NativeFairStreamDenied("duplicate or consumed request identity")
            if len(self._staged) + len(self._used) >= MAX_STAGED_PROMPTS:
                raise NativeFairStreamDenied("prompt admission capacity exhausted")
            self._staged[pinned.request_id] = pinned

    def claim(self, request_id: str, tenant_id: str) -> PinnedNativePrompt:
        """Consume before invoking a potentially side-effecting model."""
        with self._lock:
            pinned = self._staged.get(_id(request_id, "request"))
            if pinned is None or pinned.tenant_id != _id(tenant_id, "tenant"):
                raise NativeFairStreamDenied("missing authorized prompt")
            self._used.add(request_id)
            del self._staged[request_id]
            return pinned

    def revoke(self, request_id: str) -> None:
        """Burn a pending grant without authorizing an execution."""
        with self._lock:
            _id(request_id, "request")
            self._staged.pop(request_id, None)
            self._used.add(request_id)

    def status(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "schema": "skeleton.ai.native-fair-stream-prompt-status.v1",
                "staged": len(self._staged),
                "consumed_or_revoked": len(self._used),
            }


class NativeFairStreamBackend:
    """NativeLLMRuntime -> encrypted result vault's OfflineInferenceBackend.

    The application must independently authenticate tenants before staging
    prompts. Fair-stream session and journal authorize actual lease execution.
    A request can be executed only once in this process, and any failure after
    claim is outcome-uncertain to the outer durable execution owner.
    """

    def __init__(
        self, runtime: NativeLLMRuntime, registry: NativePromptRegistry,
    ) -> None:
        model, tokenizer = _cpu_runtime(runtime)
        if type(registry) is not NativePromptRegistry:
            raise NativeFairStreamDenied("canonical prompt registry required")
        self.runtime = runtime
        self.registry = registry
        self.model_digest = model
        self.tokenizer_digest = tokenizer
        self._lock = RLock()

    def _pending(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> str:
        if type(permit) is not DispatchPermit or permit.device_qualified:
            raise NativeFairStreamDenied("CPU-only canonical permit required")
        if (type(state) is not dict
                or state.get("session_id") != self.registry.session_id
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
        if (lease.get("lease_id") != permit.lease_id
                or lease.get("request_id") != permit.request_id
                or lease.get("tokens") != permit.tokens
                or lease.get("bytes_reserved") != permit.bytes_reserved):
            raise NativeFairStreamDenied("pending lease identity mismatch")
        matching = [item for item in requests
                    if type(item) is dict and item.get("request_id") == permit.request_id]
        if len(matching) != 1:
            raise NativeFairStreamDenied("missing canonical stream request")
        request = matching[0]
        bytes_per_token = request.get("bytes_per_token")
        if (type(bytes_per_token) is not int or bytes_per_token <= 0
                or type(permit.tokens) is not int or permit.tokens <= 0
                or permit.tokens * bytes_per_token != permit.bytes_reserved):
            raise NativeFairStreamDenied("lease memory accounting mismatch")
        return _id(request.get("tenant_id"), "tenant")

    def generate(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> tuple[int, bytes]:
        with self._lock:
            tenant = self._pending(permit, state)
            model, tokenizer = _cpu_runtime(self.runtime)
            if (not hmac.compare_digest(model, self.model_digest)
                    or not hmac.compare_digest(tokenizer, self.tokenizer_digest)):
                raise NativeFairStreamDenied("pinned native runtime changed")
            # Claim is intentionally irreversible, even on a preflight failure.
            pinned = self.registry.claim(permit.request_id, tenant)
            if (pinned.max_output_tokens < permit.tokens
                    or not hmac.compare_digest(pinned.model_digest, model)
                    or not hmac.compare_digest(pinned.tokenizer_digest, tokenizer)):
                raise NativeFairStreamDenied("prompt/model/output grant mismatch")
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
                result = self.runtime.generate_sequence(sequence, config)
                _cpu_runtime(self.runtime)
            except NativeFairStreamDenied:
                raise
            except Exception as exc:
                raise NativeFairStreamDenied("native inference failed; no retry") from exc
            if type(result) is not GenerationResult:
                raise NativeFairStreamDenied("untrusted native generation result")
            receipt = result.replay_receipt
            if (receipt.model_digest != model
                    or receipt.tokenizer_digest != tokenizer
                    or receipt.device_digest != self.runtime.device.digest
                    or result.prompt_sequence.token_ids != sequence.token_ids
                    or type(result.usage.generated_tokens) is not int
                    or result.usage.generated_tokens != len(result.generated_ids)
                    or result.usage.generated_tokens > permit.tokens
                    or type(result.text) is not str):
                raise NativeFairStreamDenied("native output attestation mismatch")
            try:
                output = result.text.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise NativeFairStreamDenied("invalid native output Unicode") from exc
            if len(output) > MAX_RESULT_BYTES:
                raise NativeFairStreamDenied("native output exceeds sealed vault limit")
            return result.usage.generated_tokens, output
