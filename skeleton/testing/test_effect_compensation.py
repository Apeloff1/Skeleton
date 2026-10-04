from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.skills.effect_compensation import (
    EffectCompensationConflict,
    EffectCompensationError,
    EffectIntent,
    EffectState,
    RecoveryMode,
    SQLiteEffectCompensationLedger,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def automatic() -> EffectIntent:
    return EffectIntent(
        tenant_id="tenant-a",
        operation_id="op-1",
        effect_id="charge-1",
        action="billing.charge",
        request_digest=digest("charge-request"),
        recovery_mode=RecoveryMode.AUTOMATIC_COMPENSATION,
        compensation_action="billing.refund",
        compensation_request_digest=digest("refund-request"),
    )


class EffectCompensationTests(unittest.TestCase):
    def test_non_idempotent_effect_requires_recovery_plan(self) -> None:
        with self.assertRaisesRegex(EffectCompensationError, "requires action"):
            EffectIntent(
                tenant_id="tenant-a",
                operation_id="op-1",
                effect_id="effect-1",
                action="external.write",
                request_digest=digest("request"),
                recovery_mode=RecoveryMode.AUTOMATIC_COMPENSATION,
            )
        with self.assertRaisesRegex(EffectCompensationError, "explicit reason"):
            EffectIntent(
                tenant_id="tenant-a",
                operation_id="op-1",
                effect_id="effect-1",
                action="external.write",
                request_digest=digest("request"),
                recovery_mode=RecoveryMode.MANUAL_RECONCILIATION,
            )

    def test_prepare_is_idempotent_only_for_exact_intent(self) -> None:
        with SQLiteEffectCompensationLedger() as ledger:
            first = ledger.prepare(automatic(), now_ns=100)
            second = ledger.prepare(automatic(), now_ns=101)
            self.assertEqual(first.digest, second.digest)
            changed = EffectIntent(
                tenant_id="tenant-a",
                operation_id="op-1",
                effect_id="charge-1",
                action="billing.charge",
                request_digest=digest("different"),
                recovery_mode=RecoveryMode.AUTOMATIC_COMPENSATION,
                compensation_action="billing.refund",
                compensation_request_digest=digest("refund-request"),
            )
            with self.assertRaisesRegex(EffectCompensationConflict, "reused"):
                ledger.prepare(changed, now_ns=102)

    def test_commit_receipt_is_exactly_once_and_recovery_is_explicit(self) -> None:
        with SQLiteEffectCompensationLedger() as ledger:
            ledger.prepare(automatic(), now_ns=100)
            committed = ledger.mark_committed(
                tenant_id="tenant-a",
                operation_id="op-1",
                effect_id="charge-1",
                forward_receipt_digest=digest("external-receipt"),
                now_ns=101,
            )
            self.assertEqual(committed.state, EffectState.COMMITTED)
            replay = ledger.mark_committed(
                tenant_id="tenant-a",
                operation_id="op-1",
                effect_id="charge-1",
                forward_receipt_digest=digest("external-receipt"),
                now_ns=102,
            )
            self.assertEqual(replay.digest, committed.digest)
            with self.assertRaises(EffectCompensationConflict):
                ledger.mark_committed(
                    tenant_id="tenant-a",
                    operation_id="op-1",
                    effect_id="charge-1",
                    forward_receipt_digest=digest("different-receipt"),
                    now_ns=103,
                )
            required = ledger.require_recovery(
                tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1", now_ns=104
            )
            self.assertEqual(required.state, EffectState.COMPENSATION_REQUIRED)

    def test_claim_generation_fences_concurrent_compensators(self) -> None:
        with SQLiteEffectCompensationLedger() as ledger:
            ledger.prepare(automatic(), now_ns=100)
            ledger.mark_committed(
                tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                forward_receipt_digest=digest("receipt"), now_ns=101,
            )
            ledger.require_recovery(
                tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1", now_ns=102
            )
            claim = ledger.claim_compensation(
                tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                owner_id="worker-a", expected_claim_generation=0, now_ns=103,
            )
            self.assertEqual(claim.claim_generation, 1)
            with self.assertRaisesRegex(EffectCompensationConflict, "stale"):
                ledger.claim_compensation(
                    tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                    owner_id="worker-b", expected_claim_generation=0, now_ns=104,
                )
            with self.assertRaisesRegex(EffectCompensationConflict, "foreign"):
                ledger.mark_compensated(
                    tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                    owner_id="worker-b", claim_generation=1,
                    compensation_receipt_digest=digest("refund-receipt"), now_ns=105,
                )
            done = ledger.mark_compensated(
                tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                owner_id="worker-a", claim_generation=1,
                compensation_receipt_digest=digest("refund-receipt"), now_ns=106,
            )
            self.assertEqual(done.state, EffectState.COMPENSATED)
            self.assertTrue(done.terminal)

    def test_manual_effect_never_claims_automatic_compensation(self) -> None:
        intent = EffectIntent(
            tenant_id="tenant-a",
            operation_id="op-2",
            effect_id="email-1",
            action="email.send",
            request_digest=digest("send"),
            recovery_mode=RecoveryMode.MANUAL_RECONCILIATION,
            manual_reconciliation_reason="message cannot be unsent; operator must reconcile recipient state",
        )
        with SQLiteEffectCompensationLedger() as ledger:
            ledger.prepare(intent, now_ns=100)
            ledger.mark_committed(
                tenant_id="tenant-a", operation_id="op-2", effect_id="email-1",
                forward_receipt_digest=digest("provider-receipt"), now_ns=101,
            )
            required = ledger.require_recovery(
                tenant_id="tenant-a", operation_id="op-2", effect_id="email-1", now_ns=102,
            )
            self.assertEqual(required.state, EffectState.MANUAL_REQUIRED)
            with self.assertRaisesRegex(EffectCompensationConflict, "manual-only"):
                ledger.claim_compensation(
                    tenant_id="tenant-a", operation_id="op-2", effect_id="email-1",
                    owner_id="worker", expected_claim_generation=0, now_ns=103,
                )
            done = ledger.mark_manual_resolved(
                tenant_id="tenant-a", operation_id="op-2", effect_id="email-1",
                resolution_receipt_digest=digest("ticket-closed"), now_ns=104,
            )
            self.assertEqual(done.state, EffectState.MANUAL_RESOLVED)

    def test_restart_recovers_committed_in_doubt_effects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "effects.sqlite3"
            with SQLiteEffectCompensationLedger(path) as ledger:
                ledger.prepare(automatic(), now_ns=100)
                ledger.mark_committed(
                    tenant_id="tenant-a", operation_id="op-1", effect_id="charge-1",
                    forward_receipt_digest=digest("receipt"), now_ns=101,
                )
            with SQLiteEffectCompensationLedger(path) as reopened:
                rows = reopened.in_doubt(tenant_id="tenant-a")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].state, EffectState.COMMITTED)
                self.assertEqual(rows[0].intent.effect_id, "charge-1")

    def test_tenant_scoping_prevents_cross_tenant_recovery(self) -> None:
        with SQLiteEffectCompensationLedger() as ledger:
            ledger.prepare(automatic(), now_ns=100)
            with self.assertRaises(EffectCompensationError):
                ledger.get(tenant_id="tenant-b", operation_id="op-1", effect_id="charge-1")
            self.assertEqual(ledger.in_doubt(tenant_id="tenant-b"), ())


if __name__ == "__main__":
    unittest.main()
