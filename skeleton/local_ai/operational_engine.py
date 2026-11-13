"""Legacy local-AI operational facade; never masquerade as native inference.

Real inference is exclusively provided by the guarded canonical
`skeleton.provider_runtime` boundary. This legacy interface has no model,
tokenizer, reviewer or sealed-context proof and therefore cannot produce text.
"""
from __future__ import annotations

from typing import Dict


class LocalInferenceNotActivated(RuntimeError):
    """A legacy facade was asked to generate without native model authority."""

    code = "LOCAL_GGUF_NOT_ACTIVATED"


class OperationalEngine:
    """Compatibility object that fails closed instead of fabricating output."""

    def generate(self, prompt: str, cas: str, max_tokens: int = 128) -> Dict:
        from .fail_closed import guard_cas

        guard_cas(cas)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty text")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 8192:
            raise ValueError("max_tokens must be an integer between 1 and 8192")
        raise LocalInferenceNotActivated(
            "Legacy local-AI facade cannot attest model/tokenizer/guard activation; "
            "use the canonical guarded provider runtime"
        )

    def status(self) -> Dict:
        return {
            "operational": False,
            "inference_ready": False,
            "readiness_code": LocalInferenceNotActivated.code,
            "provider_boundary": "skeleton.provider_runtime",
        }


def get_engine() -> OperationalEngine:
    return OperationalEngine()
