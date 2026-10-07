from __future__ import annotations
import unittest
from skeleton.eval.vertical_suite import DistributedExecutionFixture, DistributedOutcome, DistributedTask, VerticalSuiteError, WorkerLease

class VS006DistributedExecutionTests(unittest.TestCase):
    def test_unknown_outcome_requires_reconciliation_before_retry(self):
        fixture=DistributedExecutionFixture()
        task=DistributedTask("dist-1","idem-1","effect:external")
        with self.assertRaisesRegex(VerticalSuiteError,"requires reconciliation"):
            fixture.execute(task,WorkerLease("l1","w1",1),observed_outcome=DistributedOutcome.UNKNOWN)

    def test_stale_lease_and_duplicate_effect_are_rejected(self):
        fixture=DistributedExecutionFixture()
        task=DistributedTask("dist-1","idem-1","effect:external")
        fixture.execute(task,WorkerLease("l1","w1",1),observed_outcome=DistributedOutcome.COMMITTED)
        with self.assertRaisesRegex(VerticalSuiteError,"stale"):
            fixture.execute(task,WorkerLease("l0","w0",1),observed_outcome=DistributedOutcome.NOT_COMMITTED)
        with self.assertRaisesRegex(VerticalSuiteError,"duplicate external effect"):
            fixture.execute(task,WorkerLease("l2","w2",2),observed_outcome=DistributedOutcome.COMMITTED)

    def test_partition_unknown_can_be_recorded_with_reconciliation(self):
        receipt=DistributedExecutionFixture().execute(
            DistributedTask("dist-2","idem-2","effect:x"),
            WorkerLease("lease","worker",1),
            observed_outcome=DistributedOutcome.UNKNOWN,
            reconciliation_refs=("reconcile:journal","reconcile:provider"),
        )
        self.assertEqual(receipt.outcome,DistributedOutcome.UNKNOWN)

if __name__=="__main__": unittest.main()
