"""Pinned TLS and Ed25519 signed verdicts for an independently operated reviewer.

No model request may supply the reviewer endpoint, trust anchor, or TLS
context. The application root must deploy and audit the independent signer;
this client verifies signed evidence but cannot certify physical isolation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
from urllib.parse import urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.context.pre_delivery_guard import ReviewVerdict
from .reviewer_custody import ReviewerCustodyError, ReviewerTrustAnchor

_MAX_TEXT = 1_048_576
_MAX_RESPONSE = 8192
_DOMAIN = b"skeleton.guard.signed-review.v1\x00"


def canonical_verdict(fields: dict[str, object]) -> bytes:
    return _DOMAIN + json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


class SignedReviewerClient:
    """Sync signed preflight reviewer and async signed activation challenge."""

    def __init__(
        self, *, base_url: str, trust_anchor: ReviewerTrustAnchor,
        tls_context: ssl.SSLContext, timeout_seconds: float = 3.0,
    ) -> None:
        if type(trust_anchor) is not ReviewerTrustAnchor:
            raise ReviewerCustodyError("reviewer trust anchor required")
        if (not isinstance(tls_context, ssl.SSLContext)
                or tls_context.verify_mode != ssl.CERT_REQUIRED
                or tls_context.check_hostname is not True):
            raise ReviewerCustodyError("reviewer TLS hostname verification required")
        if type(timeout_seconds) not in (float, int) or not 0 < timeout_seconds <= 5:
            raise ReviewerCustodyError("reviewer timeout invalid")
        if type(base_url) is not str or len(base_url) > 2048:
            raise ReviewerCustodyError("reviewer endpoint invalid")
        try:
            parsed = urlsplit(base_url)
            valid = (
                parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.path in ("", "/") and not parsed.query
                and not parsed.fragment
                and all(ord(c) < 128 for c in parsed.netloc)
            )
            _ = parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ReviewerCustodyError("reviewer HTTPS endpoint required")
        self._base_url = base_url.rstrip("/")
        self._anchor = trust_anchor
        self._key = Ed25519PublicKey.from_public_bytes(
            trust_anchor.ed25519_public_key
        )
        options = dict(
            verify=tls_context, timeout=timeout_seconds, trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
        )
        self._sync = httpx.Client(**options)
        self._async = httpx.AsyncClient(**options)

    def __call__(self, untrusted_text: str, context_sha256: str) -> ReviewVerdict:
        if type(untrusted_text) is not str or type(context_sha256) is not str:
            raise ReviewerCustodyError("reviewer input invalid")
        try:
            raw = untrusted_text.encode("utf-8", errors="strict")
        except UnicodeError:
            raise ReviewerCustodyError("reviewer text invalid") from None
        if not 1 <= len(raw) <= _MAX_TEXT:
            raise ReviewerCustodyError("reviewer text exceeds bound")
        if hashlib.sha256(raw).hexdigest() != context_sha256:
            raise ReviewerCustodyError("reviewer digest mismatch")
        nonce = secrets.token_hex(24)
        request = dict(
            schema="skeleton.guard.review-request.v1", nonce=nonce,
            context_sha256=context_sha256, untrusted_text=untrusted_text,
        )
        try:
            with self._sync.stream(
                "POST", self._base_url + "/v1/review", json=request,
                headers={"Accept": "application/json"},
            ) as response:
                if response.status_code != 200:
                    raise ReviewerCustodyError("reviewer unavailable")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE:
                        raise ReviewerCustodyError("reviewer response exceeds bound")
        except ReviewerCustodyError:
            raise
        except Exception:
            raise ReviewerCustodyError("reviewer transport unavailable") from None
        try:
            doc = json.loads(body)
            required = {
                "schema", "nonce", "context_sha256", "reviewer_id",
                "allowed", "reason_code", "signature",
            }
            if type(doc) is not dict or set(doc) != required:
                raise ValueError("review fields")
            if (doc["schema"] != "skeleton.guard.signed-review.v1"
                    or doc["nonce"] != nonce
                    or doc["context_sha256"] != context_sha256
                    or doc["reviewer_id"] != self._anchor.authority_id
                    or type(doc["allowed"]) is not bool
                    or type(doc["reason_code"]) is not str
                    or not 1 <= len(doc["reason_code"]) <= 128
                    or any(not 33 <= ord(c) <= 126 for c in doc["reason_code"])
                    or type(doc["signature"]) is not str):
                raise ValueError("review binding")
            signature = base64.b64decode(doc.pop("signature"), validate=True)
            if len(signature) != 64:
                raise ValueError("review signature")
            self._key.verify(signature, canonical_verdict(doc))
        except (ValueError, TypeError, KeyError, UnicodeError, InvalidSignature):
            raise ReviewerCustodyError("signed reviewer verdict untrusted") from None
        return ReviewVerdict(
            doc["allowed"], context_sha256, self._anchor.authority_id,
            doc["reason_code"],
        )

    async def attest_challenge(self, payload: bytes) -> bytes:
        if type(payload) is not bytes or not 1 <= len(payload) <= 4096:
            raise ReviewerCustodyError("reviewer challenge invalid")
        try:
            async with self._async.stream(
                "POST", self._base_url + "/v1/attest", content=payload,
                headers={"Content-Type": "application/octet-stream"},
            ) as response:
                if response.status_code != 200:
                    raise ReviewerCustodyError("reviewer signer unavailable")
                output = bytearray()
                async for chunk in response.aiter_bytes():
                    output.extend(chunk)
                    if len(output) > 64:
                        raise ReviewerCustodyError("reviewer signature exceeds bound")
        except ReviewerCustodyError:
            raise
        except Exception:
            raise ReviewerCustodyError("reviewer signing transport unavailable") from None
        if len(output) != 64:
            raise ReviewerCustodyError("reviewer signature invalid")
        return bytes(output)

    async def aclose(self) -> None:
        await self._async.aclose()
        self._sync.close()


__all__ = ["SignedReviewerClient", "canonical_verdict"]
