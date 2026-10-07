from __future__ import annotations

import hashlib
import threading
import unittest

from skeleton.ai.learning.break_glass import (
    BreakGlassAuthority,
    BreakGlassError,
    BreakGlassGrant,
    BreakGlassReceipt,
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
            allowed_operations=(
                "disable_model",
                "rollback_known_good_checkpoint",
            ),
            target_scope=(
                "model:production-a",
                "checkpoint:known-good",
            ),
            issued_unix_s=1_000,
            expires_unix_s=1_600,
            nonce="nonce-1",
            policy_digest=sha("policy"),
            incident_ref="incident:123",
        )
        values.update(overrides)
        return BreakGlassGrant(**values)

    def request(
        self,
        grant: BreakGlassGrant,
        **overrides,
    ) -> BreakGlassRequest:
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
        self.assertEqual(receipt.sequence, 1)
        self.assertIsNone(receipt.previous_receipt_digest)

        replay = authority.evaluate(grant, self.request(grant))
        self.assertFalse(replay.admitted)
        self.assertIn("already been consumed", replay.reason)
        self.assertEqual(replay.sequence, 2)
        self.assertEqual(replay.previous_receipt_digest, receipt.digest)
        authority.assert_audit_integrity()

    def test_requester_cannot_self_approve(self) -> None:
        with self.assertRaisesRegex(BreakGlassError, "may not approve"):
            self.grant(
                approvers=(
                    "principal:operator-a",
                    "principal:security-b",
                )
            )

    def test_requires_two_unique_approvers(self) -> None:
        with self.assertRaisesRegex(
            BreakGlassError,
            "two unique approvers",
        ):
            self.grant(approvers=("principal:security-b",))

        with self.assertRaisesRegex(
            BreakGlassError,
            "two unique approvers",
        ):
            self.grant(
                approvers=(
                    "principal:security-b",
                    "principal:security-b",
                )
            )

    def test_grant_is_hard_limited_to_one_hour(self) -> None:
        with self.assertRaisesRegex(BreakGlassError, "one hour"):
            self.grant(expires_unix_s=5_000)

    def test_grant_times_must_be_nonnegative_and_ordered(self) -> None:
        with self.assertRaisesRegex(
            BreakGlassError,
            "non-negative integer",
        ):
            self.grant(issued_unix_s=-1)
        with self.assertRaisesRegex(
            BreakGlassError,
            "after issue time",
        ):
            self.grant(issued_unix_s=1000, expires_unix_s=1000)
        with self.assertRaisesRegex(
            BreakGlassError,
            "non-negative integer",
        ):
            self.grant(issued_unix_s=True)

    def test_training_and_promotion_cannot_be_granted(self) -> None:
        for operation in (
            "train_model",
            "promote_model",
            "disable_audit",
            "delete_evidence",
            "execute_arbitrary_code",
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(
                    BreakGlassError,
                    "unsafe",
                ):
                    self.grant(allowed_operations=(operation,))

    def test_grant_identity_is_order_independent_for_sets(self) -> None:
        first = self.grant()
        second = self.grant(
            approvers=tuple(reversed(first.approvers)),
            allowed_operations=tuple(
                reversed(first.allowed_operations)
            ),
            target_scope=tuple(reversed(first.target_scope)),
        )
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first, second)

    def test_grant_text_must_be_normalized(self) -> None:
        with self.assertRaisesRegex(
            BreakGlassError,
            "normalized text",
        ):
            self.grant(grant_id=" grant-1")
        with self.assertRaisesRegex(
            BreakGlassError,
            "normalized text",
        ):
            self.grant(nonce="nonce-1 ")

    def test_scope_escape_is_rejected_without_consuming_grant(self) -> None:
        grant = self.grant()
        authority = BreakGlassAuthority()
        receipt = authority.evaluate(
            grant,
            self.request(grant, target="model:other"),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("outside grant scope", receipt.reason)
        self.assertFalse(authority.consumed(grant))

        corrected = authority.evaluate(
            grant,
            self.request(grant),
        )
        self.assertTrue(corrected.admitted)
        self.assertTrue(authority.consumed(grant))

    def test_expired_grant_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(
                grant,
                now_unix_s=grant.expires_unix_s,
            ),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("expired", receipt.reason)

    def test_request_before_issue_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(
                grant,
                now_unix_s=grant.issued_unix_s - 1,
            ),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("predates grant", receipt.reason)

    def test_wrong_actor_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(
                grant,
                actor="principal:attacker",
            ),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("does not own grant", receipt.reason)

    def test_digest_tampering_is_rejected(self) -> None:
        grant = self.grant()
        receipt = BreakGlassAuthority().evaluate(
            grant,
            self.request(
                grant,
                grant_digest=sha("wrong"),
            ),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("grant digest mismatch", receipt.reason)

    def test_wrong_nonce_is_rejected_without_consumption(self) -> None:
        grant = self.grant()
        authority = BreakGlassAuthority()
        receipt = authority.evaluate(
            grant,
            self.request(grant, nonce="different-nonce"),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("nonce does not match grant", receipt.reason)
        self.assertFalse(authority.consumed(grant))

    def test_first_receipt_is_deterministic_across_fresh_authorities(self) -> None:
        grant = self.grant()
        request = self.request(grant)
        first = BreakGlassAuthority().evaluate(grant, request)
        second = BreakGlassAuthority().evaluate(grant, request)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.request_digest, request.digest)

    def test_request_identity_is_deterministic_and_time_bound(self) -> None:
        grant = self.grant()
        first = self.request(grant)
        second = self.request(grant)
        later = self.request(grant, now_unix_s=first.now_unix_s + 1)
        self.assertEqual(first.digest, second.digest)
        self.assertNotEqual(first.digest, later.digest)

    def test_register_grant_rejects_grant_id_rebinding(self) -> None:
        authority = BreakGlassAuthority()
        first = self.grant()
        authority.register_grant(first)
        rebound = self.grant(
            policy_digest=sha("different-policy"),
        )
        with self.assertRaisesRegex(
            BreakGlassError,
            "grant id is already bound",
        ):
            authority.register_grant(rebound)

    def test_evaluate_rejects_previously_bound_grant_id_rebinding(self) -> None:
        authority = BreakGlassAuthority()
        first = self.grant()
        authority.register_grant(first)
        rebound = self.grant(
            policy_digest=sha("different-policy"),
        )
        receipt = authority.evaluate(
            rebound,
            self.request(rebound),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("grant id was rebound", receipt.reason)

    def test_nonce_cannot_be_reused_across_distinct_grants(self) -> None:
        authority = BreakGlassAuthority()
        first = self.grant()
        second = self.grant(
            grant_id="grant-2",
            requester="principal:operator-b",
            nonce=first.nonce,
        )
        authority.register_grant(first)
        with self.assertRaisesRegex(
            BreakGlassError,
            "nonce is already bound",
        ):
            authority.register_grant(second)

    def test_audit_chain_digest_changes_with_each_decision(self) -> None:
        authority = BreakGlassAuthority()
        grant = self.grant()
        empty = authority.audit_chain_digest
        first = authority.evaluate(grant, self.request(grant))
        after_first = authority.audit_chain_digest
        authority.evaluate(grant, self.request(grant))
        after_second = authority.audit_chain_digest

        self.assertNotEqual(empty, after_first)
        self.assertNotEqual(after_first, after_second)
        self.assertEqual(
            authority.receipts()[0].digest,
            first.digest,
        )
        authority.assert_audit_integrity()

    def test_audit_capacity_exhaustion_refuses_to_issue_decision(self) -> None:
        authority = BreakGlassAuthority(max_receipts=1)
        grant = self.grant()
        authority.evaluate(
            grant,
            self.request(grant, target="model:other"),
        )
        before = authority.receipts()
        with self.assertRaisesRegex(
            BreakGlassError,
            "audit receipt capacity exhausted",
        ):
            authority.evaluate(grant, self.request(grant))
        self.assertEqual(authority.receipts(), before)
        self.assertFalse(authority.consumed(grant))

    def test_max_receipts_must_be_positive_integer(self) -> None:
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(BreakGlassError):
                    BreakGlassAuthority(max_receipts=value)  # type: ignore[arg-type]

    def test_concurrent_replay_race_admits_exactly_once(self) -> None:
        grant = self.grant()
        request = self.request(grant)
        authority = BreakGlassAuthority(max_receipts=64)
        barrier = threading.Barrier(16)
        receipts: list[BreakGlassReceipt] = []
        failures: list[BaseException] = []
        result_lock = threading.Lock()

        def worker() -> None:
            try:
                barrier.wait()
                receipt = authority.evaluate(grant, request)
                with result_lock:
                    receipts.append(receipt)
            except BaseException as exc:  # pragma: no cover - diagnostic
                with result_lock:
                    failures.append(exc)

        threads = [
            threading.Thread(target=worker)
            for _ in range(16)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [])
        self.assertEqual(len(receipts), 16)
        self.assertEqual(
            sum(receipt.admitted for receipt in receipts),
            1,
        )
        stored = authority.receipts()
        self.assertEqual(len(stored), 16)
        self.assertEqual(
            tuple(receipt.sequence for receipt in stored),
            tuple(range(1, 17)),
        )
        self.assertTrue(authority.consumed(grant))
        authority.assert_audit_integrity()

    def test_receipt_rejects_incoherent_admission_reason(self) -> None:
        grant = self.grant()
        request = self.request(grant)
        with self.assertRaisesRegex(
            BreakGlassError,
            "reason must be 'admitted'",
        ):
            BreakGlassReceipt(
                grant_id=grant.grant_id,
                grant_digest=grant.digest,
                operation=request.operation,
                target=request.target,
                actor=request.actor,
                admitted=True,
                reason="rejected somehow",
                incident_ref=grant.incident_ref,
                policy_digest=grant.policy_digest,
                request_digest=request.digest,
                sequence=1,
            )

    def test_receipt_requires_previous_digest_after_first_sequence(self) -> None:
        grant = self.grant()
        request = self.request(grant)
        with self.assertRaisesRegex(
            BreakGlassError,
            "requires previous digest",
        ):
            BreakGlassReceipt(
                grant_id=grant.grant_id,
                grant_digest=grant.digest,
                operation=request.operation,
                target=request.target,
                actor=request.actor,
                admitted=False,
                reason="blocked",
                incident_ref=grant.incident_ref,
                policy_digest=grant.policy_digest,
                request_digest=request.digest,
                sequence=2,
            )

    def test_authority_type_checks_inputs(self) -> None:
        authority = BreakGlassAuthority()
        grant = self.grant()
        with self.assertRaises(TypeError):
            authority.evaluate("grant", self.request(grant))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            authority.evaluate(grant, "request")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
