"""Signed reviewer transport fixtures; no live independent signer is claimed."""
from __future__ import annotations

import base64
import hashlib
import json
import ssl
import unittest
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from skeleton.ai.runtime.inference.reviewer_custody import (
    ReviewerCustodyError, ReviewerTrustAnchor, ReviewerCustodyVerifier,
)
from skeleton.ai.runtime.inference.signed_reviewer_client import (
    SignedReviewerClient, canonical_verdict,
)


class SignedReviewerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.anchor = ReviewerTrustAnchor(
            "reviewer-prod", "separate-reviewer-domain",
            self.key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )
        self.context = ssl.create_default_context()
        self.mode = "allow"
        self.calls = []
        self.client = None

    async def asyncTearDown(self):
        if self.client is not None:
            await self.client.aclose()

    def respond(self, request):
        self.calls.append(request.url.path)
        if request.url.path == "/v1/attest":
            return httpx.Response(200, content=self.key.sign(request.content))
        if request.url.path != "/v1/review":
            return httpx.Response(404)
        data = json.loads(request.content)
        fields = {
            "schema": "skeleton.guard.signed-review.v1",
            "nonce": data["nonce"],
            "context_sha256": data["context_sha256"],
            "reviewer_id": "reviewer-prod",
            "allowed": self.mode != "deny",
            "reason_code": "approved" if self.mode != "deny" else "unsafe",
        }
        signature = self.key.sign(canonical_verdict(fields))
        if self.mode == "replay":
            fields["nonce"] = "stale"
        if self.mode == "digest":
            fields["context_sha256"] = "0" * 64
        if self.mode == "unsigned":
            signature = b"invalid"
        if self.mode == "oversize":
            return httpx.Response(200, content=b"x" * 8193)
        if self.mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.invalid"})
        if self.mode == "compressed":
            return httpx.Response(200, content=b"compressed", headers={"Content-Encoding": "gzip"})
        if self.mode == "declared_oversize":
            return httpx.Response(200, content=b"{}", headers={"Content-Length": "99999999"})
        fields["signature"] = base64.b64encode(signature).decode()
        return httpx.Response(200, json=fields)

    def make(self):
        transport = httpx.MockTransport(self.respond)
        original_sync = httpx.Client
        original_async = httpx.AsyncClient
        with patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client.httpx.Client",
            side_effect=lambda **kwargs: original_sync(transport=transport, **kwargs),
        ), patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client.httpx.AsyncClient",
            side_effect=lambda **kwargs: original_async(transport=transport, **kwargs),
        ):
            self.client = SignedReviewerClient(
                base_url="https://reviewer.internal",
                trust_anchor=self.anchor, tls_context=self.context,
            )
        return self.client

    async def test_review_and_attestation_same_signer(self):
        client = self.make()
        text = "untrusted source"
        digest = hashlib.sha256(text.encode()).hexdigest()
        verdict = client(text, digest)
        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.context_sha256, digest)
        verifier = ReviewerCustodyVerifier(
            reviewer=client, authority_id="reviewer-prod",
            trust_anchor=self.anchor,
        )
        await verifier.verify(
            tenant_id="tenant", actor_id="owner", context_id="context",
            epoch=2, model_digest="a" * 64, runtime_digest="b" * 64,
            tokenizer_digest="c" * 64,
        )
        self.assertEqual(self.calls, ["/v1/review", "/v1/attest"])

    async def test_signed_deny_not_promoted(self):
        self.mode = "deny"
        client = self.make()
        text = "bad instructions"
        verdict = client(text, hashlib.sha256(text.encode()).hexdigest())
        self.assertIs(verdict.allowed, False)
        self.assertEqual(verdict.reason_code, "unsafe")

    async def test_replay_forgery_oversize_and_redirect_denied(self):
        client = self.make()
        text = "source"
        digest = hashlib.sha256(text.encode()).hexdigest()
        for mode in ("replay", "digest", "unsigned", "oversize", "redirect", "compressed", "declared_oversize"):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(ReviewerCustodyError):
                    client(text, digest)

    async def test_total_sync_review_deadline_denies_signed_response(self):
        client = self.make()
        digest = hashlib.sha256(b"source").hexdigest()
        # The signed verdict is valid, but arrives beyond the wall-clock
        # budget. A valid signature never overrides a timeout.
        with patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client._now",
            side_effect=[1.0, 10.0],
        ):
            with self.assertRaisesRegex(ReviewerCustodyError, "deadline"):
                client("source", digest)

    async def test_total_async_attestation_deadline_denies_signature(self):
        client = self.make()
        with patch(
            "skeleton.ai.runtime.inference.signed_reviewer_client._now",
            side_effect=[1.0, 10.0],
        ):
            with self.assertRaisesRegex(ReviewerCustodyError, "deadline"):
                await client.attest_challenge(b"valid challenge")

    async def test_compressed_attestation_response_denied(self):
        client = self.make()
        original = client._async
        async def cannot_produce_signature(request):
            return httpx.Response(
                200, content=b"not a signature",
                headers={"Content-Encoding": "gzip"},
            )
        await original.aclose()
        client._async = httpx.AsyncClient(transport=httpx.MockTransport(cannot_produce_signature))
        with self.assertRaisesRegex(ReviewerCustodyError, "encoded"):
            await client.attest_challenge(b"valid challenge")

    async def test_input_digest_and_size_bound(self):
        client = self.make()
        with self.assertRaises(ReviewerCustodyError):
            client("source", "0" * 64)
        with self.assertRaises(ReviewerCustodyError):
            client("x" * 1_048_577, "0" * 64)
        self.assertEqual(self.calls, [])

    async def test_https_and_tls_required(self):
        for url in (
            "http://reviewer.internal", "https://user:secret@reviewer.internal",
            "https://reviewer.internal/path", "https://reviewer.internal?secret=yes",
        ):
            with self.subTest(url=url), self.assertRaises(ReviewerCustodyError):
                SignedReviewerClient(
                    base_url=url, trust_anchor=self.anchor,
                    tls_context=self.context,
                )
        insecure = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        insecure.check_hostname = False
        insecure.verify_mode = ssl.CERT_NONE
        with self.assertRaises(ReviewerCustodyError):
            SignedReviewerClient(
                base_url="https://reviewer.internal",
                trust_anchor=self.anchor, tls_context=insecure,
            )

    async def test_bad_attestation_input_denied(self):
        client = self.make()
        for payload in (b"", b"x" * 4097):
            with self.assertRaises(ReviewerCustodyError):
                await client.attest_challenge(payload)


if __name__ == "__main__":
    unittest.main()
