"""HMAC-integrity checkpoints do not authorize releases or stale state."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.checkpoint import CheckpointAuthority
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError
class CheckpointCases(QueueCase):
    def test_verified_checkpoint_on_unchanged_state(self):
        self.store.submit(self.order)
        authority=CheckpointAuthority(b"K"*32)
        sealed=authority.seal(self.store,tenant="local",observed_at=150)
        verified=authority.verify(sealed,self.store,tenant="local")
        self.assertTrue(verified["source_state_consistent"])
        self.assertFalse(verified["release_certified"])
    def test_checkpoint_detects_new_events(self):
        signer=CheckpointAuthority(b"K"*32)
        before=signer.seal(self.store,tenant="local",observed_at=150)
        self.store.submit(self.order)
        with self.assertRaises(WorkOrderError):
            signer.verify(before,self.store,tenant="local")
    def test_tampered_hmac_or_scope_refused(self):
        self.store.submit(self.order)
        signer=CheckpointAuthority(b"K"*32)
        item=signer.seal(self.store,tenant="local",observed_at=150)
        item["body"]["tenant"]="other"
        with self.assertRaises(WorkOrderError):
            signer.verify(item,self.store,tenant="other")
