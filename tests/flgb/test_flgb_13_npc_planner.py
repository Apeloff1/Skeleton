import unittest
from skeleton.game.gameplay.npc_planner import NPCGoal, plan_npc
D="a"*64
class TestNPCPlanner(unittest.TestCase):
    def test_risk_gate_precedes_utility(self):
        risky=NPCGoal("risky",1000000,900000,D)
        safe=NPCGoal("safe",700000,100000,D)
        plan=plan_npc((risky,safe),500000)
        self.assertEqual([g.goal_id for g in plan],["safe"])
if __name__=="__main__": unittest.main()
