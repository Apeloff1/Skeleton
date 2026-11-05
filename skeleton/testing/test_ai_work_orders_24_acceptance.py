"""Contract-only first native work acceptance and persisted budget behavior."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.acceptance import run_live
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError
class AcceptanceCases(QueueCase):
    def run_once(self,**changes):
        kwargs=dict(worker=self.worker,queue_dir=self.state_dir,
                    tenant="local",subject="owner",prompt_text="hello",
                    operator_key=b"K"*32,now_seconds=150,
                    token_ceiling=10000,max_output_tokens=64)
        kwargs.update(changes)
        return run_live(**kwargs)
    def test_signed_work_replay_and_budget_with_contract_double(self):
        outcome=self.run_once()
        self.assertEqual(outcome["source_state"],
                         "actual-supervisor-canonical-SQLite-replay")
        self.assertEqual(self.worker.generation_calls,1)
        self.assertFalse(outcome["release_certified"])
    def test_second_run_preserves_consumed_tokens(self):
        first=self.run_once()
        before=self.store.budget("local")["consumed"]
        second=self.run_once()
        self.assertEqual(self.worker.generation_calls,2)
        self.assertEqual(self.store.budget("local")["consumed"],
                         before+second["charged_tokens"])
    def test_existing_budget_cannot_be_silently_increased(self):
        with self.assertRaises(WorkOrderError):
            self.run_once(token_ceiling=20000)
        self.assertEqual(self.worker.generation_calls,0)
    def test_wrong_principal_refused_before_model(self):
        with self.assertRaises(WorkOrderError):
            self.run_once(tenant="other")
        self.assertEqual(self.worker.generation_calls,0)
if __name__=="__main__":unittest.main()
