"""Durable offline AI work-order regression; contract-only test worker, no real GGUF claimed."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class QuotaTamperCases(QueueCase):
    def test_reserved_totals_detect_tampering(self):
        self.store.submit(self.order)
        self.store.claim(self.order,expected_revision=1,reservation_tokens=128)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE budgets SET reserved=reserved-1 WHERE tenant='local'")
        with self.assertRaises(WorkOrderError):self.store.audit()
    def test_charged_totals_detect_tampering(self):
        self.store.submit(self.order)
        self.executor.run(self.order,self.prompt)
        with self.store.db.transaction() as conn:
            conn.execute("UPDATE budgets SET consumed=consumed+1 WHERE tenant='local'")
        with self.assertRaises(WorkOrderError):self.store.audit()
    def test_budget_negative_refused_by_sqlite_check(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db.transaction() as conn:
                conn.execute("UPDATE budgets SET consumed=-1 WHERE tenant='local'")

if __name__=="__main__":unittest.main()
