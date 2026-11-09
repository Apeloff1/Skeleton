"""Byte-bound model-serving admission.

Caller supplies trusted expected SHA-256 digests from a separately authorized
deployment policy. Never treat untrusted request metadata as that policy.
"""
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable

from .admission import ServingPolicy, admit


@dataclass(frozen=True)
class ServingRequest:
    backend: str
    context_tokens: int
    output_tokens: int


class AdmissionDenied(PermissionError):
    """No backend execution is permitted."""


def verified_invoke(
    policy: ServingPolicy,
    request: ServingRequest,
    *,
    model_bytes: bytes,
    evaluation_bytes: bytes,
    invoke: Callable[[ServingRequest], object],
) -> object:
    """Verify artifact bytes and admission *before* invoking a backend.

    The callback is an already-authorized backend adapter, not an arbitrary
    request-supplied function. This does not validate evaluation semantics.
    """
    if not isinstance(request, ServingRequest) or not callable(invoke):
        raise AdmissionDenied("invalid serving request or backend")
    if type(model_bytes) is not bytes or type(evaluation_bytes) is not bytes:
        raise AdmissionDenied("artifact evidence must be immutable bytes")
    if not model_bytes or not evaluation_bytes:
        raise AdmissionDenied("empty artifact or evaluation evidence")
    model_digest = "sha256:" + sha256(model_bytes).hexdigest()
    evaluation_digest = "sha256:" + sha256(evaluation_bytes).hexdigest()
    if not admit(
        policy,
        model_digest=model_digest,
        evaluation_digest=evaluation_digest,
        backend=request.backend,
        context_tokens=request.context_tokens,
        output_tokens=request.output_tokens,
    ):
        raise AdmissionDenied("model serving admission denied")
    return invoke(request)
