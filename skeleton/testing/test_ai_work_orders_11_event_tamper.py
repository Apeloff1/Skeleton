"""Tamper tests use transactionally permissible alterations, not FK violations."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError
class EventTamperCases(QueueCase):
    def test_event_payload_change_triggers_integrity_hold(self):
        self.store.submit(self.order)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE events SET body=? WHERE sequence=1",(b'{"forged":true}',))
        with self.assertRaises(WorkOrderError):self.store.audit()
    def test_changed_event_parent_digest_triggers_hold(self):
        self.store.submit(self.order)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE events SET previous_sha=? WHERE sequence=1",("c"*64,))
        with self.assertRaises(WorkOrderError):self.store.audit()
    def test_mutated_job_state_without_event_triggers_hold(self):
        self.store.submit(self.order)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE jobs SET status='committed' WHERE job_id=?",(self.order.job_id,))
        with self.assertRaises(WorkOrderError):self.store.audit()
if __name__=="__main__":unittest.main()
