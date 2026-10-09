"""Fail-closed, side-effect-free serving admission.

This checks *identifiers* and budgets; upstream callers must independently
verify model bytes, evaluation evidence, and deployment authorization.
"""
from dataclasses import dataclass
import hmac
import re

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ServingPolicy:
    model_digest: str
    evaluation_digest: str
    backend: str
    max_context_tokens: int
    max_output_tokens: int


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _backend(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is not None


def _budget(value: object) -> bool:
    return type(value) is int and value > 0


def admit(policy: ServingPolicy, *, model_digest: str, evaluation_digest: str,
          backend: str, context_tokens: int, output_tokens: int) -> bool:
    """Admit only exact policy identities and bounded token requests."""
    if not isinstance(policy, ServingPolicy):
        return False
    if not (_digest(policy.model_digest) and _digest(model_digest)
            and _digest(policy.evaluation_digest) and _digest(evaluation_digest)
            and _backend(policy.backend) and _backend(backend)):
        return False
    if not (_budget(policy.max_context_tokens)
            and _budget(policy.max_output_tokens)
            and type(context_tokens) is int and context_tokens >= 0
            and _budget(output_tokens)):
        return False
    return (hmac.compare_digest(policy.model_digest, model_digest)
            and hmac.compare_digest(policy.evaluation_digest, evaluation_digest)
            and hmac.compare_digest(policy.backend, backend)
            and context_tokens <= policy.max_context_tokens
            and output_tokens <= policy.max_output_tokens)
