import unittest
from skeleton.game.gameplay.npc_planner import GameplayContractError, NPCAction, plan_npc
class T(unittest.TestCase):
 def test_goal_plan(self):
  acts=(NPCAction("get_key",(),("key",),1),NPCAction("open",("key",),("door_open",),1))
  self.assertEqual(plan_npc(acts,(),"door_open"),("get_key","open"))
  with self.assertRaises(GameplayContractError): plan_npc((),(),"x")
if __name__=="__main__": unittest.main()
