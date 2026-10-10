import unittest
from skeleton.game.simulation.transform_hierarchy import SimulationContractError, TransformHierarchy, TransformNode

class TestTransformHierarchy(unittest.TestCase):
    def test_world_position_and_cycle_detection(self):
        h=TransformHierarchy((TransformNode("root",None,(1,2,3)),TransformNode("child","root",(4,5,6))))
        self.assertEqual(h.world_position("child"),(5,7,9))
        with self.assertRaises(SimulationContractError):
            TransformHierarchy((TransformNode("a","b",(0,0,0)),TransformNode("b","a",(0,0,0))))

if __name__=="__main__": unittest.main()
