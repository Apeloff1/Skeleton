import unittest
from skeleton.ai.forge.forge_10000_cycle import forge_10000

class TestForge10000(unittest.TestCase):
    def test_cycle_budget_is_exact(self):
        plan=forge_10000(10,100000)
        self.assertEqual((plan.tier,plan.cycles),("forge-10000",10000))

if __name__=="__main__": unittest.main()
