import unittest
from skeleton.ai.forge.forge_1000_cycle import forge_1000

class TestForge1000(unittest.TestCase):
    def test_cycle_budget_is_exact(self):
        plan=forge_1000(100,150000)
        self.assertEqual((plan.tier,plan.cycles),("forge-1000",1000))

if __name__=="__main__": unittest.main()
