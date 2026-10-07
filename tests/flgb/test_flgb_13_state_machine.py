import unittest
from skeleton.game.gameplay.state_machine import GameplayContractError, StateMachine, StateTransition
class TestStateMachine(unittest.TestCase):
    def test_transitions_reference_declared_states(self):
        sm=StateMachine(("idle","combat"),(StateTransition("engage","idle","combat"),),"idle")
        self.assertEqual(sm.next_states("idle"),("combat",))
        with self.assertRaises(GameplayContractError):
            StateMachine(("idle",),(StateTransition("bad","idle","missing"),),"idle")
if __name__=="__main__": unittest.main()
