from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from skeleton.kernel.side_effect_compensation import (
    AmbiguousExternalOutcome,
    COMPENSATED,
    COMPENSATION_DISPATCHED,
    COMPENSATION_REQUIRED,
    CompensationConflict,
    FORWARD_DISPATCHED,
    FORWARD_NO_EFFECT,
    FORWARD_SUCCEEDED,
    MANUAL_REVIEW,
    PREPARED,
    SQLiteCompensationLedger,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SideEffectCompensationTests(unittest.TestCase):
    def test_prepare_is_identity_bound_and_idempotent(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            first = ledger.prepare(
                tenant_id="t",
                operation_id="op",
                request_digest=digest("request"),
                forward_action="billing.charge",
                compensation_action="billing.refund",
            )
            second = ledger.prepare(
                tenant_id="t",
                operation_id="op",
                request_digest=digest("request"),
                forward_action="billing.charge",
                compensation_action="billing.refund",
            )
            self.assertEqual(first, second)
            self.assertEqual(first.state, PREPARED)
            with self.assertRaisesRegex(CompensationConflict, "changed"):
                ledger.prepare(
                    tenant_id="t",
                    operation_id="op",
                    request_digest=digest("different"),
                    forward_action="billing.charge",
                    compensation_action="billing.refund",
                )

    def test_forward_success_then_compensation_is_receipt_bound(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("request"),
                forward_action="billing.charge",
                compensation_action="billing.refund",
            )
            record = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("forward-dispatch"),
            )
            self.assertEqual(record.state, FORWARD_DISPATCHED)
            record = ledger.record_forward_success(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                receipt_digest=digest("charge-receipt"),
            )
            self.assertEqual(record.state, FORWARD_SUCCEEDED)
            record = ledger.require_compensation(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                reason_digest=digest("downstream-failure"),
            )
            self.assertEqual(record.state, COMPENSATION_REQUIRED)
            record = ledger.mark_compensation_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("refund-dispatch"),
            )
            self.assertEqual(record.state, COMPENSATION_DISPATCHED)
            record = ledger.record_compensated(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                receipt_digest=digest("refund-receipt"),
            )
            self.assertEqual(record.state, COMPENSATED)
            self.assertTrue(record.terminal)

    def test_forward_dispatch_crash_window_is_never_auto_replayed(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="external.create",
                compensation_action="external.delete",
            )
            record = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("dispatch"),
            )
            candidate = ledger.recovery_candidates()[0]
            self.assertEqual(candidate.action, "reconcile_forward_outcome")
            self.assertFalse(candidate.auto_dispatch_safe)
            with self.assertRaises(AmbiguousExternalOutcome):
                ledger.assert_safe_to_dispatch_forward(record)

    def test_compensation_dispatch_crash_window_is_never_auto_replayed(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="external.create",
                compensation_action="external.delete",
            )
            record = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("fd"),
            )
            record = ledger.record_forward_success(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                receipt_digest=digest("fr"),
            )
            record = ledger.require_compensation(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                reason_digest=digest("reason"),
            )
            record = ledger.mark_compensation_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("cd"),
            )
            candidate = ledger.recovery_candidates()[0]
            self.assertEqual(candidate.action, "reconcile_compensation_outcome")
            self.assertFalse(candidate.auto_dispatch_safe)
            with self.assertRaises(AmbiguousExternalOutcome):
                ledger.assert_safe_to_dispatch_compensation(record)

    def test_confirmed_no_effect_is_terminal_without_compensation(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="external.create",
                compensation_action="external.delete",
            )
            record = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("fd"),
            )
            record = ledger.record_forward_no_effect(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                evidence_digest=digest("provider-confirmed-no-effect"),
            )
            self.assertEqual(record.state, FORWARD_NO_EFFECT)
            self.assertTrue(record.terminal)
            self.assertEqual(ledger.recovery_candidates(), ())

    def test_manual_review_is_evidence_bound_terminal_state(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="external.create",
                compensation_action="external.delete",
            )
            record = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("fd"),
            )
            record = ledger.mark_manual_review(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                evidence_digest=digest("incident"),
            )
            self.assertEqual(record.state, MANUAL_REVIEW)
            self.assertTrue(record.terminal)
            with self.assertRaises(CompensationConflict):
                ledger.mark_manual_review(
                    tenant_id="t", operation_id="op",
                    expected_version=record.version,
                    evidence_digest=digest("again"),
                )

    def test_stale_version_cannot_repeat_external_transition(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            prepared = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="external.create",
                compensation_action="external.delete",
            )
            dispatched = ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=prepared.version,
                dispatch_digest=digest("fd"),
            )
            with self.assertRaises(CompensationConflict):
                ledger.record_forward_success(
                    tenant_id="t", operation_id="op",
                    expected_version=prepared.version,
                    receipt_digest=digest("receipt"),
                )
            self.assertEqual(
                ledger.require(tenant_id="t", operation_id="op"),
                dispatched,
            )

    def test_restart_preserves_ambiguous_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compensation.sqlite"
            with SQLiteCompensationLedger(path) as first:
                record = first.prepare(
                    tenant_id="t", operation_id="op",
                    request_digest=digest("r"),
                    forward_action="external.create",
                    compensation_action="external.delete",
                )
                first.mark_forward_dispatched(
                    tenant_id="t", operation_id="op",
                    expected_version=record.version,
                    dispatch_digest=digest("fd"),
                )
            with SQLiteCompensationLedger(path) as second:
                candidate = second.recovery_candidates()[0]
                self.assertEqual(
                    candidate.record.state,
                    FORWARD_DISPATCHED,
                )
                self.assertEqual(
                    candidate.action,
                    "reconcile_forward_outcome",
                )
                self.assertFalse(candidate.auto_dispatch_safe)

    def test_tenants_are_isolated_even_when_operation_ids_match(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            a = ledger.prepare(
                tenant_id="a", operation_id="same",
                request_digest=digest("a"),
                forward_action="x", compensation_action="undo-x",
            )
            b = ledger.prepare(
                tenant_id="b", operation_id="same",
                request_digest=digest("b"),
                forward_action="y", compensation_action="undo-y",
            )
            self.assertNotEqual(a.request_digest, b.request_digest)
            self.assertEqual(
                len(ledger.recovery_candidates(tenant_id="a")),
                1,
            )
            self.assertEqual(
                len(ledger.recovery_candidates(tenant_id="b")),
                1,
            )

    def test_card_exposes_ambiguity_without_claiming_completion(self) -> None:
        with SQLiteCompensationLedger() as ledger:
            record = ledger.prepare(
                tenant_id="t", operation_id="op",
                request_digest=digest("r"),
                forward_action="x", compensation_action="undo-x",
            )
            ledger.mark_forward_dispatched(
                tenant_id="t", operation_id="op",
                expected_version=record.version,
                dispatch_digest=digest("fd"),
            )
            card = ledger.card()
            self.assertEqual(card["gap"], "G015")
            self.assertEqual(card["ambiguous_forward_count"], 1)
            self.assertFalse(card["completion_checkbox"])
            self.assertFalse(card["verification_signature"])

    def test_canonical_and_governed_ai_files_are_byte_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        canonical = root / "skeleton/kernel/side_effect_compensation.py"
        mirror = root / "skeleton/ai/runtime/kernel/side_effect_compensation.py"
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
