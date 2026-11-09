import unittest
from skeleton.game.simulation.deterministic_simulation import SimulationContractError, SimulationState
D="a"*64
E="b"*64

class TestDeterministicSimulation(unittest.TestCase):
    def test_tick_advances_once_with_stable_system_order(self):
        state=SimulationState(0,D,D,D,D,D,("input","physics","gameplay"))
        nxt=state.next(ecs_digest=E,transform_digest=D,physics_digest=E,rng_state_digest=D,input_digest=E)
        self.assertEqual(nxt.tick,1)
        self.assertEqual(nxt.system_order,state.system_order)
        with self.assertRaises(SimulationContractError):
            SimulationState(0,D,D,D,D,D,("physics","physics"))

if __name__=="__main__": unittest.main()
