"""Fail-closed, explicit admission wrapper for Skeleton's local inference engine.

Cryptography validates bytes and order, not a model's understanding. A
reviewer improves detection but is never proof of zero prompt injections.
Callers must obtain the snapshot root from independently authorized state.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from contextvars import copy_context
import asyncio
import hashlib
import json
import math
import re
import threading
import time
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from skeleton.context.delivery_regex import match_delivery_regex, validate_delivery_regex
from skeleton.context.delivery_schema import (
    parse_and_validate_delivery_json,
    validate_delivery_schema,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextIntegrityError,
    SealedContextLimitError,
)

_DOMAIN = b"skeleton.local.pre_delivery.merkle.v1\x00"
_MAX_PART_BYTES = 4 * 1024 * 1024
_MAX_PARTS = 2002
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _token_id_digest(tokens: Sequence[int]) -> str:
    """Commit to the exact native token sequence, not just its decoded text."""
    if isinstance(tokens, (str, bytes)) or not hasattr(tokens, "__len__"):
        raise SealedContextLimitError("tokenizer returned invalid or unbounded sequence")
    try:
        count = len(tokens)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SealedContextLimitError("tokenizer sequence length cannot be verified") from exc
    if type(count) is not int or count > 8_000_000 or count < 0:
        raise SealedContextLimitError("tokenizer returned invalid or unbounded sequence")
    digest = hashlib.sha256(b"skeleton.context.native-token-ids.v1\x00")
    digest.update(count.to_bytes(8, "big"))
    observed = 0
    for token in tokens:
        if type(token) is not int or token < 0 or token >= 1 << 64:
            raise SealedContextError("native token IDs are not bounded unsigned integers")
        digest.update(token.to_bytes(8, "big"))
        observed += 1
        if observed > count:
            raise SealedContextLimitError("tokenizer sequence length changed during verification")
    if observed != count:
        raise SealedContextLimitError("tokenizer sequence length changed during verification")
    return digest.hexdigest()


def _schema_snapshot(schema: Mapping[str, Any] | None) -> str | None:
    """Freeze mutable schema mappings at the admission boundary."""
    if schema is None:
        return None
    validate_delivery_schema(schema)
    try:
        return json.dumps(dict(schema), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise SealedContextError("schema snapshot could not be serialized") from exc


def _leaf(index: int, name: str, data: bytes) -> bytes:
    return hashlib.sha256(
        _DOMAIN + b"leaf\x00" + index.to_bytes(4, "big")
        + name.encode("ascii") + b"\x00" + len(data).to_bytes(8, "big") + data
    ).digest()


def merkle_root(parts: Sequence[tuple[str, bytes]]) -> str:
    """Deterministic domain-separated Merkle commitment, including positions."""
    if not 2 <= len(parts) <= _MAX_PARTS:
        raise SealedContextLimitError("invalid live context segment count")
    leaves = []
    for index, (name, value) in enumerate(parts):
        if name not in {"system", "user", "assistant"} or not isinstance(value, bytes):
            raise SealedContextError("invalid live context segment")
        if len(value) > _MAX_PART_BYTES:
            raise SealedContextLimitError("live segment exceeds byte limit")
        leaves.append(_leaf(index, name, value))
    while len(leaves) > 1:
        if len(leaves) & 1:
            leaves.append(leaves[-1])
        leaves = [hashlib.sha256(_DOMAIN + b"node\x00" + leaves[i]
                                 + leaves[i + 1]).digest()
                  for i in range(0, len(leaves), 2)]
    return leaves[0].hex()


def verify_rendered_spans(
    parts: Sequence[tuple[str, bytes]], rendered: bytes,
) -> tuple[tuple[int, int], ...]:
    """Require all original context segments verbatim and in chronological order.

    Native templates may add delimiters but must not erase, trim or rearrange
    source bytes. Source inclusion is not a proof of attention or role semantics.
    """
    if not isinstance(rendered, bytes) or len(rendered) > _MAX_PART_BYTES:
        raise SealedContextLimitError("rendered prompt exceeds byte admission")
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for role, payload in parts:
        if role not in {"system", "user", "assistant"} or not isinstance(payload, bytes):
            raise SealedContextError("invalid source span")
        if not payload:
            offsets.append((cursor, cursor))
            continue
        index = rendered.find(payload, cursor)
        if index < 0:
            raise SealedContextIntegrityError("native renderer omitted or changed context bytes")
        cursor = index + len(payload)
        offsets.append((index, cursor))
    return tuple(offsets)


def request_parts(request: Any) -> tuple[tuple[str, bytes], ...]:
    """Exact role-bound spans with bounded allocation BEFORE Merkle hashing."""
    from itertools import islice

    try:
        history = tuple(islice(iter(request.history), 2001))
        if len(history) > 2000:
            raise SealedContextLimitError("local history exceeds the 2,000-record cap")
        ordered = (("system", request.instructions), *history, ("user", request.prompt))
        pieces: list[tuple[str, bytes]] = []
        total_bytes = 0
        for index, entry in enumerate(ordered):
            if (not isinstance(entry, tuple) or len(entry) != 2
                    or type(entry[0]) is not str or type(entry[1]) is not str):
                raise SealedContextError("malformed local inference role/span")
            role, text = entry
            if ((index == 0 and role != "system")
                    or (index == len(ordered) - 1 and role != "user")
                    or (0 < index < len(ordered) - 1 and role not in {"user", "assistant"})):
                raise SealedContextError("local inference history contains unsupported role")
            encoded = text.encode("utf-8", errors="strict")
            total_bytes += len(encoded)
            if len(encoded) > _MAX_PART_BYTES or total_bytes > 16 * 1024 * 1024:
                raise SealedContextLimitError("local inference context exceeds byte admission")
            pieces.append((role, encoded))
    except SealedContextError:
        raise
    except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
        raise SealedContextError("malformed local inference prompt") from exc
    result = tuple(pieces)
    merkle_root(result)
    return result


@dataclass(frozen=True, slots=True)
class TrustedContextSnapshot:
    """Authority-sourced hash; never adopt the digest sent by the client."""

    root: str
    policy_sha256: str
    snapshot_version: int
    tenant_id: str
    context_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, str) or not _DIGEST.fullmatch(self.root):
            raise SealedContextError("invalid pinned context root")
        if not isinstance(self.policy_sha256, str) or not _DIGEST.fullmatch(self.policy_sha256):
            raise SealedContextError("invalid pinned instruction digest")
        if type(self.snapshot_version) is not int or self.snapshot_version < 1:
            raise SealedContextError("invalid snapshot version")
        if not self.tenant_id or not self.context_id:
            raise SealedContextBoundaryError("snapshot authority is missing")


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    allowed: bool
    context_sha256: str
    reviewer_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class _PreflightEvidence:
    root: str
    token_echo: str | None
    token_sequence_digest: str | None
    untrusted_text: str
    untrusted_sha256: str
    request_digest: Any
    delivery_schema: str | None
    native_schema: str | None


class BoundedAdversarialReviewer(Protocol):
    def __call__(self, untrusted_text: str, context_sha256: str) -> ReviewVerdict: ...


@dataclass(frozen=True, slots=True)
class DeliveryContract:
    """Native sampler enforcement is mandatory for a hard format claim."""

    format: str = "text"  # text / json / regex
    pattern: str | None = None
    json_schema: Mapping[str, Any] | None = None
    require_sampler_enforcement: bool = True

    def __post_init__(self) -> None:
        if self.format not in {"text", "json", "regex"}:
            raise SealedContextError("unsupported output format")
        if self.format == "regex":
            validate_delivery_regex(self.pattern)
        if self.format == "json":
            validate_delivery_schema(self.json_schema)


@dataclass(frozen=True, slots=True)
class PreDeliveryReceipt:
    context_root: str
    token_echo_sha256: str | None
    reviewer_id: str
    request_digest: str
    response_sha256: str
    token_sequence_sha256: str | None = None


class GuardedLocalInference:
    """Composition over LocalInferenceEngine; it does not own model credentials.

    A trusted caller supplies snapshot and scope, reviewer, and (when required)
    tokenizer byte round-trip and native sampler attestation. Caches are only
    reachable after preflight. Output is withheld until postflight validation.
    """

    def __init__(
        self, engine: Any, *,
        reviewer: BoundedAdversarialReviewer,
        tokenize: Callable[[str], Sequence[int]] | None = None,
        detokenize: Callable[[Sequence[int]], str] | None = None,
        sampler_support: Callable[[Any, DeliveryContract], bool] | None = None,
        projection_attestor: Callable[[Any, str, str], bool] | None = None,
        tokenizer_identity_attestor: Callable[[], bool] | None = None,
        require_token_echo: bool = True,
        review_timeout_seconds: float = 5.0,
        native_timeout_seconds: float = 5.0,
    ) -> None:
        if not hasattr(engine, "generate") or not callable(reviewer):
            raise SealedContextError("local engine and independent reviewer are required")
        if (isinstance(review_timeout_seconds, bool)
                or not isinstance(review_timeout_seconds, (int, float))
                or not math.isfinite(review_timeout_seconds)
                or not 0 < review_timeout_seconds <= 30):
            raise SealedContextError("review timeout must be finite and within 30 seconds")
        if (isinstance(native_timeout_seconds, bool)
                or not isinstance(native_timeout_seconds, (int, float))
                or not math.isfinite(native_timeout_seconds)
                or not 0 < native_timeout_seconds <= 30):
            raise SealedContextError("native verification timeout must be finite and within 30 seconds")
        self.engine = engine
        self.reviewer = reviewer
        self.tokenize = tokenize
        self.detokenize = detokenize
        self.sampler_support = sampler_support
        self.projection_attestor = projection_attestor
        self.tokenizer_identity_attestor = tokenizer_identity_attestor
        self.require_token_echo = require_token_echo
        self.review_timeout_seconds = float(review_timeout_seconds)
        self.native_timeout_seconds = float(native_timeout_seconds)
        # A stuck reviewer retains its slot until the underlying call returns.
        # Timeouts/cancellations do not create an unbounded queue of workers.
        self._review_slot = threading.BoundedSemaphore(1)
        # A blocked native tokenizer/renderer cannot queue unlimited workers.
        # A timed-out call retains this reservation until it actually exits.
        self._native_verification_slot = threading.BoundedSemaphore(1)

    @staticmethod
    def _native_callback(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Keep backend-controlled exceptions out of client errors and logs."""
        try:
            return callback(*args, **kwargs)
        except Exception:
            # Renderers/tokenizers can include private input bytes in exception
            # messages and chained tracebacks. Guard-owned validation below
            # still emits its distinct integrity and boundary reason codes.
            raise SealedContextBoundaryError("native verification callback unavailable") from None

    def _attest_tokenizer_identity(self) -> None:
        verifier = self.tokenizer_identity_attestor
        if verifier is None:
            return
        try:
            verified = verifier()
        except Exception:
            raise SealedContextBoundaryError("native tokenizer identity verification unavailable") from None
        if verified is not True:
            raise SealedContextIntegrityError("native tokenizer identity changed")

    def _preflight_evidence(
        self, request: Any, *, snapshot: TrustedContextSnapshot,
        tenant_scope_id: str, contract: DeliveryContract,
    ) -> _PreflightEvidence:
        delivery_schema = _schema_snapshot(contract.json_schema) if contract.format == "json" else None
        native_schema = (
            _schema_snapshot(getattr(request, "structured_output_schema", None))
            if delivery_schema is not None and contract.require_sampler_enforcement else None
        )
        self._attest_tokenizer_identity()
        if snapshot.tenant_id != tenant_scope_id:
            raise SealedContextBoundaryError("context snapshot crossed tenant boundary")
        parts = request_parts(request)
        actual_root = merkle_root(parts)
        if actual_root != snapshot.root:
            raise SealedContextIntegrityError("local context bytes differ from trusted snapshot")
        if _hash(parts[0][1]) != snapshot.policy_sha256:
            raise SealedContextIntegrityError("trusted core instruction bytes changed")
        if getattr(request, "context_digest", None) not in {None, snapshot.root}:
            raise SealedContextIntegrityError("request context digest mismatches authority")
        # Mirror the actual backend prompt renderer when it supplies one.
        # Checking only the generic user-facing representation can miss
        # provider-specific formatting or special-token insertion.
        native_renderer = getattr(self.engine.model, "_render_prompt", None)
        rendered = self._native_callback(native_renderer, request) if callable(native_renderer) else request.rendered_input
        if not isinstance(rendered, str):
            raise SealedContextError("local rendered prompt must be text")
        # A lossless tokenizer echo is not evidence that a native renderer kept
        # every instruction/history segment. Demand a separately trusted
        # projection attestor whenever the backend changes prompt formatting.
        if callable(native_renderer) and rendered != request.rendered_input:
            if self.projection_attestor is None or self._native_callback(
                self.projection_attestor, request, rendered, actual_root
            ) is not True:
                raise SealedContextIntegrityError(
                    "native prompt projection did not attest exact context preservation"
                )
        encoded = rendered.encode("utf-8", errors="strict")
        if len(encoded) > _MAX_PART_BYTES:
            raise SealedContextLimitError("local rendered prompt exceeds byte admission")
        verify_rendered_spans(parts, encoded)
        token_digest: str | None = None
        token_sequence_digest: str | None = None
        if self.require_token_echo and (self.tokenize is None or self.detokenize is None):
            raise SealedContextBoundaryError("native tokenizer echo verification is not configured")
        if self.tokenize is not None and self.detokenize is not None:
            tokens = self._native_callback(self.tokenize, rendered)
            token_sequence_digest = _token_id_digest(tokens)
            if self._native_callback(self.detokenize, tokens).encode("utf-8", errors="strict") != encoded:
                raise SealedContextIntegrityError("native tokenizer round trip changed input bytes")
            token_digest = _hash(encoded)
        untrusted = "\n".join(text for _, text in request.history) + "\n" + request.prompt
        context_sha = _hash(untrusted.encode("utf-8", errors="strict"))
        return _PreflightEvidence(actual_root, token_digest, token_sequence_digest,
                                  untrusted, context_sha, getattr(request, "digest", None),
                                  delivery_schema, native_schema)

    def _finish_preflight(
        self, request: Any, *, contract: DeliveryContract,
        evidence: _PreflightEvidence, verdict: Any,
    ) -> tuple[str, str | None, str, str | None]:
        if (not isinstance(verdict, ReviewVerdict) or verdict.allowed is not True
                or verdict.context_sha256 != evidence.untrusted_sha256
                or not isinstance(verdict.reviewer_id, str) or not verdict.reviewer_id.strip()
                or len(verdict.reviewer_id) > 256
                or not isinstance(verdict.reason_code, str) or not verdict.reason_code.strip()
                or len(verdict.reason_code) > 256):
            raise SealedContextBoundaryError("adversarial review declined or was unbound")
        if contract.format != "text" and contract.require_sampler_enforcement:
            if contract.format == "json" and contract.json_schema is not None:
                configured = getattr(request, "structured_output_schema", None)
                if (not isinstance(configured, Mapping)
                        or _schema_snapshot(configured) != _schema_snapshot(contract.json_schema)):
                    raise SealedContextBoundaryError(
                        "native JSON sampler request is not bound to delivery schema"
                    )
            if self.sampler_support is None or self._native_callback(self.sampler_support, self.engine.model, contract) is not True:
                raise SealedContextBoundaryError("local sampler lacks required grammar constraint")
        return evidence.root, evidence.token_echo, verdict.reviewer_id, evidence.token_sequence_digest

    def preflight(
        self, request: Any, *, snapshot: TrustedContextSnapshot,
        tenant_scope_id: str, contract: DeliveryContract,
    ) -> tuple[str, str | None, str, str | None]:
        """Synchronous admission for callers that manage their own deadline.

        The asynchronous generation path uses bounded review instead.
        """
        if not self._native_verification_slot.acquire(blocking=False):
            raise SealedContextBoundaryError("native verification is busy")
        try:
            evidence = self._preflight_evidence(
                request, snapshot=snapshot, tenant_scope_id=tenant_scope_id, contract=contract,
            )
            if not self._review_slot.acquire(blocking=False):
                raise SealedContextBoundaryError("adversarial reviewer is busy")
            try:
                try:
                    verdict = self.reviewer(evidence.untrusted_text, evidence.untrusted_sha256)
                except Exception:
                    raise SealedContextBoundaryError("adversarial reviewer unavailable") from None
            finally:
                self._review_slot.release()
            return self._finish_preflight(request, contract=contract, evidence=evidence, verdict=verdict)
        finally:
            self._native_verification_slot.release()

    async def _bounded_native_call(self, operation: Callable[[], Any], timeout: float) -> Any:
        """Bound native callback latency and retain physical capacity after timeout.

        Callbacks may validate or prepare data but must never dispatch a model
        or publish output. Context variables are copied for the engine's
        worker-only preparation permit; the asyncio owner task is not moved.
        """
        if not self._native_verification_slot.acquire(blocking=False):
            raise SealedContextBoundaryError("native verification is busy")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[bool, Any]] = loop.create_future()
        context = copy_context()

        def run() -> None:
            try:
                result = (True, context.run(operation))
            except BaseException as exc:
                result = (False, exc)
            finally:
                self._native_verification_slot.release()

            def deliver() -> None:
                if not future.done():
                    future.set_result(result)

            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                # A timed-out caller may have closed its event loop already.
                pass

        try:
            threading.Thread(target=run, name="skeleton-local-native-check", daemon=True).start()
        except Exception as exc:
            self._native_verification_slot.release()
            raise SealedContextBoundaryError("native verification worker unavailable") from exc
        except BaseException:
            self._native_verification_slot.release()
            raise
        try:
            ok, value = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except TimeoutError as exc:
            raise SealedContextBoundaryError("native verification timed out") from exc
        if not ok:
            if isinstance(value, SealedContextError):
                raise value
            raise SealedContextBoundaryError("native verification unavailable") from None
        return value

    async def _bounded_review(self, evidence: _PreflightEvidence, timeout: float) -> tuple[Any, Any]:
        if not self._review_slot.acquire(blocking=False):
            raise SealedContextBoundaryError("adversarial reviewer is busy")
        reviewer = self.reviewer
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()

        def run_review() -> None:
            try:
                verdict = reviewer(evidence.untrusted_text, evidence.untrusted_sha256)
                failed = False
            except BaseException:
                verdict = None
                failed = True
            finally:
                self._review_slot.release()

            def deliver() -> None:
                if future.done():
                    return
                if failed:
                    future.set_exception(SealedContextBoundaryError("adversarial reviewer unavailable"))
                else:
                    future.set_result(verdict)

            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                # The requesting event loop may have closed after a timeout.
                pass

        try:
            threading.Thread(target=run_review, name="skeleton-local-review", daemon=True).start()
        except Exception as exc:
            self._review_slot.release()
            raise SealedContextBoundaryError("adversarial reviewer worker unavailable") from exc
        except BaseException:
            self._review_slot.release()
            raise

        # A timed-out/cancelled caller must not cancel the shared worker or
        # leave a late exception unobserved. Python cannot kill a stuck thread.
        def observe(done: asyncio.Future[Any]) -> None:
            if not done.cancelled():
                done.exception()

        future.add_done_callback(observe)
        try:
            verdict = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            return reviewer, verdict
        except TimeoutError as exc:
            raise SealedContextBoundaryError("adversarial reviewer timed out") from exc
        except Exception:
            raise SealedContextBoundaryError("adversarial reviewer unavailable") from None

    @staticmethod
    def _assert_request_matches_evidence(request: Any, contract: DeliveryContract, evidence: _PreflightEvidence) -> None:
        """Recheck caller-owned bytes after an awaited authority/worker boundary."""
        if (merkle_root(request_parts(request)) != evidence.root
                or getattr(request, "digest", None) != evidence.request_digest):
            raise SealedContextIntegrityError("local input changed during guarded admission")
        delivery_schema = _schema_snapshot(contract.json_schema) if contract.format == "json" else None
        native_schema = (
            _schema_snapshot(getattr(request, "structured_output_schema", None))
            if delivery_schema is not None and contract.require_sampler_enforcement else None
        )
        if delivery_schema != evidence.delivery_schema or native_schema != evidence.native_schema:
            raise SealedContextIntegrityError("local schema changed during guarded admission")

    def _validate_delivery(
        self, request: Any, result: Any, *, contract: DeliveryContract,
        evidence: _PreflightEvidence, reviewer_id: str,
        pinned_schema: str | None, pinned_native_schema: str | None,
    ) -> tuple[Any, PreDeliveryReceipt]:
        """Validate native output without blocking the asyncio event loop."""
        root, token_echo, admitted_token_ids = evidence.root, evidence.token_echo, evidence.token_sequence_digest
        self._attest_tokenizer_identity()
        after_parts = request_parts(request)
        if merkle_root(after_parts) != root:
            raise SealedContextIntegrityError("local input mutated during generation")
        native_renderer = getattr(self.engine.model, "_render_prompt", None)
        after_rendered = self._native_callback(native_renderer, request) if callable(native_renderer) else request.rendered_input
        if not isinstance(after_rendered, str):
            raise SealedContextIntegrityError("local renderer changed during inference")
        after_bytes = after_rendered.encode("utf-8", errors="strict")
        verify_rendered_spans(after_parts, after_bytes)
        if token_echo is not None and _hash(after_bytes) != token_echo:
            raise SealedContextIntegrityError("native model input changed during inference")
        if admitted_token_ids is not None:
            if self.tokenize is None or self.detokenize is None:
                raise SealedContextBoundaryError("admitted tokenizer is no longer available")
            after_tokens = self._native_callback(self.tokenize, after_rendered)
            if _token_id_digest(after_tokens) != admitted_token_ids:
                raise SealedContextIntegrityError("native token ID sequence changed during inference")
            if self._native_callback(self.detokenize, after_tokens).encode("utf-8", errors="strict") != after_bytes:
                raise SealedContextIntegrityError("native tokenizer echo changed during inference")
        if callable(native_renderer) and after_rendered != request.rendered_input:
            if self.projection_attestor is None or self._native_callback(
                self.projection_attestor, request, after_rendered, root
            ) is not True:
                raise SealedContextIntegrityError("native prompt projection attestation changed during inference")
        if contract.format != "text" and contract.require_sampler_enforcement:
            if self.sampler_support is None or self._native_callback(self.sampler_support, self.engine.model, contract) is not True:
                raise SealedContextBoundaryError("native sampler grammar is no longer attested at delivery")
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise SealedContextError("local model did not produce text")
        if contract.format == "json":
            if _schema_snapshot(contract.json_schema) != pinned_schema:
                raise SealedContextIntegrityError("delivery schema mutated during inference")
            if pinned_native_schema is not None and (
                _schema_snapshot(getattr(request, "structured_output_schema", None)) != pinned_native_schema
            ):
                raise SealedContextIntegrityError("native sampler schema mutated during inference")
            parse_and_validate_delivery_json(text, json.loads(pinned_schema) if pinned_schema is not None else None)
        elif contract.format == "regex":
            match_delivery_regex(text, contract.pattern)
        return result, PreDeliveryReceipt(root, token_echo, reviewer_id, request.digest,
                                          _hash(text.encode("utf-8")), admitted_token_ids)

    async def generate(
        self, request: Any, *, snapshot: TrustedContextSnapshot,
        tenant_scope_id: str, contract: DeliveryContract = DeliveryContract(),
        _before_dispatch: Callable[[], Awaitable[None]] | None = None,
        **engine_options: Any,
    ) -> tuple[Any, PreDeliveryReceipt]:
        if "tenant_scope_id" in engine_options or "prepared_input" in engine_options:
            raise SealedContextBoundaryError("caller cannot override verified local scopes")
        deadline = engine_options.get("deadline")

        def remaining_timeout(limit: float) -> float:
            if deadline is None:
                return limit
            if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
                    or not math.isfinite(deadline)):
                raise SealedContextBoundaryError("local inference deadline is invalid")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SealedContextBoundaryError("local inference deadline elapsed during admission")
            return min(limit, remaining)

        evidence = await self._bounded_native_call(
            lambda: self._preflight_evidence(
                request, snapshot=snapshot, tenant_scope_id=tenant_scope_id, contract=contract,
            ), remaining_timeout(self.native_timeout_seconds),
        )
        reviewer, verdict = await self._bounded_review(evidence, remaining_timeout(self.review_timeout_seconds))

        def finish_admission():
            after_review = self._preflight_evidence(
                request, snapshot=snapshot, tenant_scope_id=tenant_scope_id, contract=contract,
            )
            if after_review != evidence:
                raise SealedContextIntegrityError("local input changed during adversarial review")
            return self._finish_preflight(request, contract=contract, evidence=evidence, verdict=verdict)

        root, token_echo, reviewer_id, _ = await self._bounded_native_call(
            finish_admission, remaining_timeout(self.native_timeout_seconds),
        )
        self._assert_request_matches_evidence(request, contract, evidence)
        if reviewer is not self.reviewer:
            raise SealedContextIntegrityError("adversarial reviewer changed during admission")

        def verified_scope():
            if not getattr(self.engine, "require_guarded_context", False):
                return nullcontext()
            admit = getattr(self.engine, "_verified_guard_scope", None)
            if not callable(admit):
                raise SealedContextBoundaryError("protected engine lacks verified scope")
            return admit(
                request, context_root=root, token_echo=token_echo,
                reviewer_id=reviewer_id, guard_identity=self,
            )

        # Preparation can tokenize native inputs, so it uses the same bounded
        # worker slot. The engine's task-bound permit explicitly allows a
        # context-copied worker to prepare, but never to dispatch inference.
        prepare = getattr(self.engine, "prepare_input", None)
        if callable(prepare):
            with verified_scope():
                prepared = await self._bounded_native_call(
                    lambda: self._native_callback(
                        prepare, request, scope_id=engine_options.get("scope_id"),
                        tenant_scope_id=tenant_scope_id,
                    ),
                    remaining_timeout(self.native_timeout_seconds),
                )
            if prepared is not None:
                engine_options["prepared_input"] = prepared

        # The source authority remains bound to this exact asyncio task. It
        # runs outside the engine permit and after all awaited preparation so
        # neither the callback nor a timed-out worker can dispatch inference.
        if _before_dispatch is not None:
            try:
                async with asyncio.timeout(remaining_timeout(self.review_timeout_seconds)):
                    await _before_dispatch()
            except TimeoutError as exc:
                raise SealedContextBoundaryError("canonical authority timed out before dispatch") from exc
        self._assert_request_matches_evidence(request, contract, evidence)
        if reviewer is not self.reviewer:
            raise SealedContextIntegrityError("adversarial reviewer changed during admission")
        remaining_timeout(self.native_timeout_seconds)
        with verified_scope():
            result = await self.engine.generate(
                request, tenant_scope_id=tenant_scope_id, **engine_options,
            )

        delivery = await self._bounded_native_call(
            lambda: self._validate_delivery(
                request, result, contract=contract, evidence=evidence, reviewer_id=reviewer_id,
                pinned_schema=evidence.delivery_schema, pinned_native_schema=evidence.native_schema,
            ), remaining_timeout(self.native_timeout_seconds),
        )
        self._assert_request_matches_evidence(request, contract, evidence)
        remaining_timeout(self.native_timeout_seconds)
        return delivery
