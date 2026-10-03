from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.break_glass import (
    BreakGlassAuthority,
    BreakGlassError,
    BreakGlassGrant,
    BreakGlassRequest,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class BreakGlassAuthorityTests(unittest.TestCase):
    def grant(self, **overrides) -> BreakGlassGrant:
        values = dict(
            grant_id="grant-1",
            requester="principal:operator-a",
            approvers=("principal:security-b", "principal:incident-c"),
            allowed_operations=("disable_model", "rollback_known_good_checkpoint"),
            target_scope=("model:production-a", "checkpoint:known-good"),
            issued_unix_s=1_000,
            expires_unix_s=1_600,
            nonce="nonce-1",
            policy_digest=sha("policy"),
            incident_ref="incident:123",
        )
        values.update(overrides)
        return BreakGlassGrant(**values)

    def request(self, grant: BreakGlassGrant, **overrides) -> BreakGlassRequest:
        values = dict(
            grant_digest=grant.digest,
            operation="disable_model",
            target="model:production-a",
            actor=grant.requester,
            now_unix_s=1_100,
            nonce=grant.nonce,
        )
        values.update(overrides)
        return BreakGlassRequest(**values)

    def test_valid_narrow_emergency_action_is_admitted_once(self) -> None:
        grant = self.grant()
        authority = BreakGlassAuthority()
        receipt = authority.evaluate(grant, self.request(grant))
        self.assertTrue(receipt.admitted, receipt.reason)
        self.assertTrue(authority.consumed(grant))
        replay = authority.evaluate(grant, self.request(grant))
        self.assertFalse(replay.admitted)
        self.assertIn("already been consumed", replay.reason)

    def test_requester_cannot_self_approve(self) -> None:
        with self.assertRaisesRegex(BreakGlassError, "may not approve"):
            self.grant(
                approvers=("principal:operator-a", "principal:security-b")
            )

    def test_requires_two_unique_approvers(self) -> None:
        with self.assertRaisesRegex(BreakGlassError, "two unique approvers"):
            self.grant(approvers=("principal:security-b",))

    def test_grant_is_hard_limited_to_one_hour(self) -> None:
        with self.assertRaisesRegex(BreakGlassError, "one hour"):
            self.grant(expires_unix_s=5_000)

    def test_training_and_promotion_cannot_be_granted(self) -> None:
        for operation in ("train_model", "promote_model", "disable_audit"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(BreakGlassError, "unsafe"):
                    self.grant(allowed_operations=(operation,))

    def test_scope_escape_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(grant, target="model:other"),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("outside grant scope", receipt.reason)

    def test_expired_grant_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(grant, now_unix_s=grant.expires_unix_s),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("expired", receipt.reason)

    def test_wrong_actor_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(grant, actor="principal:attacker"),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("does not own grant", receipt.reason)

    def test_digest_tampering_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(grant, grant_digest=sha("wrong")),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("grant digest mismatch", receipt.reason)

    def test_receipt_identity_is_deterministic(self) -> None:
        grant = self.grant()
        first = BreakGlassAuthority().evaluate(grant, self.request(grant))
        second = BreakGlassAuthority().evaluate(grant, self.request(grant))
        self.assertEqual(first.digest, second.digest)


if __name__ == "__main__":
    unittest.main()
