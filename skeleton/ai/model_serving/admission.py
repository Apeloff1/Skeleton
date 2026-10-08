"""Deterministic, fail-closed admission contract for model serving."""
from dataclasses import dataclass
import hmac


@dataclass(frozen=True)
class ServingPolicy:
    model_digest: str
    evaluation_digest: str
    backend: str
    max_context_tokens: int
    max_output_tokens: int


def admit(policy: ServingPolicy, *, model_digest: str, evaluation_digest: str,
          backend: str, context_tokens: int, output_tokens: int) -> bool:
    """Reject missing provenance, unknown backends, and invalid token budgets."""
    if not all((policy.model_digest, policy.evaluation_digest, policy.backend,
                model_digest, evaluation_digest, backend)):
        return False
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in
               (policy.max_context_tokens, policy.max_output_tokens,
                context_tokens, output_tokens)):
        return False
    if min(policy.max_context_tokens, policy.max_output_tokens) <= 0:
        return False
    if context_tokens < 0 or output_tokens <= 0:
        return False
    return (hmac.compare_digest(policy.model_digest, model_digest)
            and hmac.compare_digest(policy.evaluation_digest, evaluation_digest)
            and hmac.compare_digest(policy.backend, backend)
            and context_tokens <= policy.max_context_tokens
            and output_tokens <= policy.max_output_tokens)
