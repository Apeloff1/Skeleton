"""Fresh Ed25519 challenge proof for an independently administered reviewer.

The application root pins the public key and supplies a reviewer client whose
private signer must live in a separately administered trust domain. Signatures
prove possession, not actual deployment isolation or review policy quality.
No secret or signature is accepted from model prompts or request metadata.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_ATTEST_TIMEOUT_SECONDS = 2.0
_DOMAIN = "skeleton.guard.reviewer-custody.v1"


class ReviewerCustodyError(RuntimeError):
    """Reviewer signer is unavailable, stale, mismatched or untrusted."""


def _identifier(value: object) -> bool:
    return (
        type(value) is str and 1 <= len(value) <= 128
        and value == value.strip()
        and all(33 <= ord(ch) <= 126 for ch in value)
    )


@dataclass(frozen=True, slots=True)
class ReviewerTrustAnchor:
    """Trusted public key pinned by the application, never client-supplied."""

    authority_id: str
    deployment_domain: str
    ed25519_public_key: bytes

    def __post_init__(self) -> None:
        if (not _identifier(self.authority_id)
                or not _identifier(self.deployment_domain)
                or self.deployment_domain == self.authority_id
                or type(self.ed25519_public_key) is not bytes
                or len(self.ed25519_public_key) != 32):
            raise ReviewerCustodyError("reviewer trust anchor invalid")
        try:
            Ed25519PublicKey.from_public_bytes(self.ed25519_public_key)
        except Exception:
            raise ReviewerCustodyError("reviewer trust anchor unavailable") from None


class ReviewerCustodyVerifier:
    """A fresh challenge for every activation and pre/postflight probe."""

    def __init__(
        self, *, reviewer: Any, authority_id: str,
        trust_anchor: ReviewerTrustAnchor,
    ) -> None:
        if (type(trust_anchor) is not ReviewerTrustAnchor
                or not _identifier(authority_id)
                or trust_anchor.authority_id != authority_id
                or not callable(reviewer)
                or not inspect.iscoroutinefunction(
                    getattr(reviewer, "attest_challenge", None)
                )):
            raise ReviewerCustodyError("independent reviewer signing client required")
        self._reviewer = reviewer
        self._anchor = trust_anchor
        self._public_key = Ed25519PublicKey.from_public_bytes(
            trust_anchor.ed25519_public_key
        )

    async def verify(
        self, *, tenant_id: str, actor_id: str, context_id: str, epoch: int,
        model_digest: str, runtime_digest: str, tokenizer_digest: str,
    ) -> None:
        if type(epoch) is not int or epoch < 2 or epoch % 2:
            raise ReviewerCustodyError("reviewer epoch invalid")
        for scope in (tenant_id, actor_id, context_id):
            if (type(scope) is not str or not scope or scope != scope.strip()
                    or len(scope.encode("utf-8", "strict")) > 512
                    or any(ord(c) < 32 for c in scope)):
                raise ReviewerCustodyError("reviewer scope invalid")
        for digest in (model_digest, runtime_digest, tokenizer_digest):
            if (type(digest) is not str or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)):
                raise ReviewerCustodyError("reviewer artifact binding invalid")
        payload = json.dumps(
            {
                "schema": _DOMAIN,
                "nonce": secrets.token_hex(24),
                "authority_id": self._anchor.authority_id,
                "deployment_domain": self._anchor.deployment_domain,
                "tenant_id": tenant_id, "actor_id": actor_id,
                "context_id": context_id, "epoch": epoch,
                "model_digest": model_digest,
                "runtime_digest": runtime_digest,
                "tokenizer_digest": tokenizer_digest,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        if len(payload) > 4096:
            raise ReviewerCustodyError("reviewer challenge exceeds bound")
        try:
            async with asyncio.timeout(_ATTEST_TIMEOUT_SECONDS):
                signature = await self._reviewer.attest_challenge(payload)
        except Exception:
            raise ReviewerCustodyError("reviewer attestation unavailable") from None
        if type(signature) is not bytes or len(signature) != 64:
            raise ReviewerCustodyError("reviewer signature invalid")
        try:
            self._public_key.verify(signature, payload)
        except (InvalidSignature, ValueError, TypeError):
            raise ReviewerCustodyError("reviewer signature not trusted") from None


__all__ = [
    "ReviewerCustodyError", "ReviewerTrustAnchor", "ReviewerCustodyVerifier",
]
