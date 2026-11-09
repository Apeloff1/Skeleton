import unittest
from skeleton.game.gameplay.state_machine import GameplayContractError, StateMachine, StateTransition
class T(unittest.TestCase):
 def test_deterministic_transition(self):
  m=StateMachine("idle",(StateTransition("idle","see","alert"),))
  self.assertEqual(m.step("idle","see"),"alert")
  with self.assertRaises(GameplayContractError): m.step("idle","missing")
if __name__=="__main__": unittest.main()
