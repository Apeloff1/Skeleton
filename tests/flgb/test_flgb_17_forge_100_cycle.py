import unittest
from skeleton.ai.forge.forge_100_cycle import ForgeContractError, forge_100

class TestForge100(unittest.TestCase):
    def test_cycle_budget_is_exact(self):
        plan=forge_100(1000,200000)
        self.assertEqual((plan.tier,plan.cycles),("forge-100",100))
        with self.assertRaises(ForgeContractError):
            type(plan)("forge-100",99,1000,200000)

if __name__=="__main__": unittest.main()
