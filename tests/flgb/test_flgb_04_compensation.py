import unittest
from skeleton.ai.agents.compensation import CompensationAction, compensation_order
D="a"*64
class TestCompensation(unittest.TestCase):
    def test_compensation_reverses_commit_order(self):
        actions=(CompensationAction("a",D,D),CompensationAction("b",D,D))
        self.assertEqual([a.action_id for a in compensation_order(actions)],["b","a"])
if __name__=="__main__": unittest.main()
