import unittest
from skeleton.ai.assurance.rollback_orchestration import AssuranceContractError, RollbackStep, rollback_plan
D="a"*64

class TestRollback(unittest.TestCase):
    def test_rollback_reverses_forward_sequence(self):
        steps=(RollbackStep(0,"a",D,D),RollbackStep(1,"b",D,D),RollbackStep(2,"c",D,D))
        self.assertEqual([x.action_id for x in rollback_plan(steps)],["c","b","a"])
        with self.assertRaises(AssuranceContractError):
            rollback_plan((RollbackStep(1,"x",D,D),))

if __name__=="__main__": unittest.main()
