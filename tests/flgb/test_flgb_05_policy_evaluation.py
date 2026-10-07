import unittest
from skeleton.security.policy_evaluation import PolicyRule, evaluate_policy
class TestPolicy(unittest.TestCase):
    def test_explicit_deny_wins_and_default_denies(self):
        rules=(PolicyRule("allow","allow","read",("member",)),PolicyRule("deny","deny","read",("blocked",)))
        self.assertEqual(evaluate_policy("read",("member",),rules).effect,"allow")
        self.assertEqual(evaluate_policy("read",("member","blocked"),rules).effect,"deny")
        self.assertEqual(evaluate_policy("write",("member",),rules).effect,"deny")
if __name__=="__main__": unittest.main()
