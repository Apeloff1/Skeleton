"""Deterministic signed reviewer authority tests; no live signer qualification."""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from skeleton.ai.runtime.inference.reviewer_custody import (
    ReviewerCustodyError, ReviewerCustodyVerifier, ReviewerTrustAnchor,
)


class SigningReviewer:
    def __init__(self, key):
        self.key = key
        self.messages = []
        self.replay = None
        self.failure = None
        self.wait = None

    def __call__(self, *args):
        return True

    async def attest_challenge(self, payload):
        self.messages.append(payload)
        if self.failure is not None:
            raise self.failure
        if self.wait is not None:
            await self.wait.wait()
        return self.replay if self.replay is not None else self.key.sign(payload)


class ReviewerCustodyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.reviewer = SigningReviewer(self.key)
        self.anchor = ReviewerTrustAnchor(
            "security-reviewer-prod", "independent-reviewer-cluster",
            self.key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ),
        )
        self.verifier = ReviewerCustodyVerifier(
            reviewer=self.reviewer, authority_id="security-reviewer-prod",
            trust_anchor=self.anchor,
        )
        self.kwargs = dict(
            tenant_id="tenant", actor_id="owner", context_id="thread",
            epoch=2, model_digest="a" * 64, runtime_digest="b" * 64,
            tokenizer_digest="c" * 64,
        )

    async def test_fresh_nonce_and_scope_binding(self):
        await self.verifier.verify(**self.kwargs)
        await self.verifier.verify(**self.kwargs)
        self.assertNotEqual(*self.reviewer.messages)
        doc = json.loads(self.reviewer.messages[0])
        self.assertEqual(doc["schema"], "skeleton.guard.reviewer-custody.v1")
        self.assertEqual(doc["epoch"], 2)
        self.assertEqual(doc["model_digest"], "a" * 64)
        self.assertEqual(doc["deployment_domain"], "independent-reviewer-cluster")
        self.assertEqual(len(doc["nonce"]), 48)

    async def test_replay_and_other_signer_denied(self):
        await self.verifier.verify(**self.kwargs)
        self.reviewer.replay = self.key.sign(self.reviewer.messages[0])
        with self.assertRaisesRegex(ReviewerCustodyError, "not trusted"):
            await self.verifier.verify(**self.kwargs)
        self.reviewer.replay = None
        self.reviewer.key = Ed25519PrivateKey.generate()
        with self.assertRaisesRegex(ReviewerCustodyError, "not trusted"):
            await self.verifier.verify(**self.kwargs)

    async def test_invalid_scope_epoch_and_digest_fail_before_signing(self):
        for field, value in (
            ("tenant_id", ""), ("actor_id", " owner "),
            ("context_id", "x" * 513), ("epoch", 3), ("epoch", True),
            ("model_digest", "x" * 64), ("tokenizer_digest", "bad"),
        ):
            with self.subTest(field=field), self.assertRaises(ReviewerCustodyError):
                await self.verifier.verify(**(self.kwargs | {field: value}))
        self.assertEqual(self.reviewer.messages, [])

    async def test_untrusted_anchor_denied(self):
        for authority, domain, key in (
            ("", "separate", self.anchor.ed25519_public_key),
            ("security-reviewer-prod", "security-reviewer-prod", self.anchor.ed25519_public_key),
            ("security-reviewer-prod", "separate", b"short"),
        ):
            with self.assertRaises(ReviewerCustodyError):
                ReviewerTrustAnchor(authority, domain, key)
        with self.assertRaises(ReviewerCustodyError):
            ReviewerCustodyVerifier(
                reviewer=self.reviewer, authority_id="wrong",
                trust_anchor=self.anchor,
            )

    async def test_errors_redacted_and_timeout_bounded(self):
        self.reviewer.failure = RuntimeError("secret reviewer key")
        with self.assertRaises(ReviewerCustodyError) as caught:
            await self.verifier.verify(**self.kwargs)
        self.assertNotIn("secret", str(caught.exception))
        self.reviewer.failure = None
        self.reviewer.wait = asyncio.Event()
        with patch(
            "skeleton.ai.runtime.inference.reviewer_custody._ATTEST_TIMEOUT_SECONDS",
            0.01,
        ):
            with self.assertRaisesRegex(ReviewerCustodyError, "unavailable"):
                await self.verifier.verify(**self.kwargs)

    async def test_cancellation_propagates(self):
        self.reviewer.wait = asyncio.Event()
        task = asyncio.create_task(self.verifier.verify(**self.kwargs))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
