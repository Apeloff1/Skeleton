"""Fail-closed, explicit admission wrapper for Skeleton's local inference engine.

Cryptography validates bytes and order, not a model's understanding. A
reviewer improves detection but is never proof of zero prompt injections.
Callers must obtain the snapshot root from independently authorized state.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

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


def request_parts(request: Any) -> tuple[tuple[str, bytes], ...]:
    """Uses exact request data, not stripped/normalized rendered model text."""
    try:
        history = tuple(request.history)
        pieces = (("system", request.instructions.encode("utf-8")),) + tuple(
            (role, text.encode("utf-8")) for role, text in history
        ) + (("user", request.prompt.encode("utf-8")),)
    except (AttributeError, TypeError, UnicodeError, ValueError) as exc:
        raise SealedContextError("malformed local inference prompt") from exc
    merkle_root(pieces)
    return pieces


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
        if self.format == "regex" and (
            not isinstance(self.pattern, str) or not 1 <= len(self.pattern) <= 2048
        ):
            raise SealedContextError("regex output requires bounded pattern")
        if self.format == "json" and self.json_schema is not None:
            if not isinstance(self.json_schema, Mapping):
                raise SealedContextError("JSON schema must be a mapping")
            if len(json.dumps(dict(self.json_schema)).encode("utf-8")) > 64 * 1024:
                raise SealedContextLimitError("JSON schema exceeds budget")


@dataclass(frozen=True, slots=True)
class PreDeliveryReceipt:
    context_root: str
    token_echo_sha256: str | None
    reviewer_id: str
    request_digest: str
    response_sha256: str


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
        require_token_echo: bool = True,
    ) -> None:
        if not hasattr(engine, "generate") or not callable(reviewer):
            raise SealedContextError("local engine and independent reviewer are required")
        self.engine = engine
        self.reviewer = reviewer
        self.tokenize = tokenize
        self.detokenize = detokenize
        self.sampler_support = sampler_support
        self.require_token_echo = require_token_echo

    def preflight(
        self, request: Any, *, snapshot: TrustedContextSnapshot,
        tenant_scope_id: str, contract: DeliveryContract,
    ) -> tuple[str, str | None, str]:
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
        rendered = native_renderer(request) if callable(native_renderer) else request.rendered_input
        if not isinstance(rendered, str):
            raise SealedContextError("local rendered prompt must be text")
        encoded = rendered.encode("utf-8", errors="strict")
        if len(encoded) > _MAX_PART_BYTES:
            raise SealedContextLimitError("local rendered prompt exceeds byte admission")
        token_digest: str | None = None
        if self.require_token_echo and (self.tokenize is None or self.detokenize is None):
            raise SealedContextBoundaryError("native tokenizer echo verification is not configured")
        if self.tokenize is not None and self.detokenize is not None:
            tokens = self.tokenize(rendered)
            if isinstance(tokens, (str, bytes)) or len(tokens) > 8_000_000:
                raise SealedContextLimitError("tokenizer returned invalid or unbounded sequence")
            if any(type(token) is not int or token < 0 for token in tokens):
                raise SealedContextError("token IDs must be non-negative integers")
            if self.detokenize(tokens).encode("utf-8", errors="strict") != encoded:
                raise SealedContextIntegrityError("native tokenizer round trip changed input bytes")
            token_digest = _hash(encoded)
        untrusted = "\n".join(text for _, text in request.history) + "\n" + request.prompt
        context_sha = _hash(untrusted.encode("utf-8", errors="strict"))
        verdict = self.reviewer(untrusted, context_sha)
        if (not isinstance(verdict, ReviewVerdict) or not verdict.allowed
                or verdict.context_sha256 != context_sha or not verdict.reviewer_id
                or not verdict.reason_code):
            raise SealedContextBoundaryError("adversarial review declined or was unbound")
        if contract.format != "text" and contract.require_sampler_enforcement:
            if self.sampler_support is None or not self.sampler_support(self.engine.model, contract):
                raise SealedContextBoundaryError("local sampler lacks required grammar constraint")
        return actual_root, token_digest, verdict.reviewer_id

    async def generate(
        self, request: Any, *, snapshot: TrustedContextSnapshot,
        tenant_scope_id: str, contract: DeliveryContract = DeliveryContract(),
        **engine_options: Any,
    ) -> tuple[Any, PreDeliveryReceipt]:
        root, token_echo, reviewer_id = self.preflight(
            request, snapshot=snapshot, tenant_scope_id=tenant_scope_id, contract=contract,
        )
        if "tenant_scope_id" in engine_options or "prepared_input" in engine_options:
            raise SealedContextBoundaryError("caller cannot override verified local scopes")
        # Reuse the engine's model-native prepared input when available.
        # LocalInferenceEngine validates its request, model and scope binding
        # before admitting inference; clients cannot supply prepared tensors.
        prepare = getattr(self.engine, "prepare_input", None)
        if callable(prepare):
            prepared = prepare(
                request, scope_id=engine_options.get("scope_id"),
                tenant_scope_id=tenant_scope_id,
            )
            if prepared is not None:
                engine_options["prepared_input"] = prepared
        result = await self.engine.generate(
            request, tenant_scope_id=tenant_scope_id, **engine_options,
        )
        if merkle_root(request_parts(request)) != root:
            raise SealedContextIntegrityError("local input mutated during generation")
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise SealedContextError("local model did not produce text")
        if contract.format == "json":
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError) as exc:
                raise SealedContextError("local JSON output violates format contract") from exc
            schema = contract.json_schema
            if schema is not None:
                # This is intentionally a small supported subset, not JSON Schema certification.
                if schema.get("type") == "object" and not isinstance(parsed, dict):
                    raise SealedContextError("local JSON output is not an object")
                required = schema.get("required", ())
                if not isinstance(required, (list, tuple)) or any(
                    not isinstance(name, str) for name in required
                ):
                    raise SealedContextError("unsupported JSON subset in delivery contract")
                if not isinstance(parsed, dict) or any(key not in parsed for key in required):
                    raise SealedContextError("local JSON output misses required keys")
        elif contract.format == "regex":
            try:
                match = re.fullmatch(contract.pattern or "", text)
            except re.error as exc:
                raise SealedContextError("invalid output regex") from exc
            if match is None:
                raise SealedContextError("local output failed grammar contract")
        return result, PreDeliveryReceipt(
            root, token_echo, reviewer_id, request.digest, _hash(text.encode("utf-8"))
        )
