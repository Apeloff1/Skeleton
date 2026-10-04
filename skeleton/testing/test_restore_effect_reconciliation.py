from datetime import datetime, timezone
import unittest
from skeleton.reliability.restore_effect_reconciliation import RestoredEffect, RestoreEffectFenceError, assert_restore_effects_safe, reconcile_restored_effects
from skeleton.skills.tool_contract import ToolExecutionRequest
from skeleton.skills.tool_effect_reconciliation import ReconciliableToolReceiptStore, ToolEffectReconciliationEvidence

def request():
    return ToolExecutionRequest(request_id="req-1", operation_id="op-1", execution_id="exec-1", turn_id="turn-1", call_id="call-1", tenant_id="tenant-1", tool_id="tool-1", idempotency_key="idem-1", arguments_digest="a"*64)

class TestRestoreEffectReconciliation(unittest.TestCase):
    def setUp(self):
        self.store=ReconciliableToolReceiptStore(); self.req=request(); self.store.reserve(self.req)
    def test_pending_without_evidence_blocks(self):
        report=reconcile_restored_effects(self.store,[RestoredEffect(self.req)])
        self.assertFalse(report.safe_to_resume)
        with self.assertRaises(RestoreEffectFenceError): assert_restore_effects_safe(report)
    def test_committed_evidence_terminalizes(self):
        ev=ToolEffectReconciliationEvidence(decision="effect_committed",observer_id="provider-a",authority_ref="external-ledger:v7",evidence_refs=("receipt:42",),observed_at=datetime(2026,10,5,tzinfo=timezone.utc),result_ref="external-result:42")
        report=reconcile_restored_effects(self.store,[RestoredEffect(self.req,ev)])
        self.assertTrue(report.safe_to_resume); assert_restore_effects_safe(report)
    def test_unknown_reservation_blocks(self):
        report=reconcile_restored_effects(ReconciliableToolReceiptStore(),[RestoredEffect(self.req)])
        self.assertFalse(report.safe_to_resume)
    def test_duplicate_identity_fails_closed(self):
        with self.assertRaises(RestoreEffectFenceError): reconcile_restored_effects(self.store,[RestoredEffect(self.req),RestoredEffect(self.req)])
