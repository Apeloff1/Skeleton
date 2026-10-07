import unittest
from skeleton.game.simulation.transform_hierarchy import SimulationContractError, TransformHierarchy, TransformNode

class TestTransforms(unittest.TestCase):
    def test_world_position_is_integer_and_cycles_fail(self):
        h=TransformHierarchy((TransformNode("root",None,10,0,0),TransformNode("child","root",5,2,0)))
        self.assertEqual(h.world_position("child"),(15,2,0))
        with self.assertRaises(SimulationContractError):
            TransformHierarchy((TransformNode("a","b",0,0,0),TransformNode("b","a",0,0,0)))

if __name__=="__main__": unittest.main()
