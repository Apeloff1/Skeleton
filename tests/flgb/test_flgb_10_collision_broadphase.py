import unittest
from skeleton.game.simulation.collision_broadphase import AABB, broadphase_pairs

class TestBroadphase(unittest.TestCase):
    def test_pairs_are_stable_and_only_overlap(self):
        boxes=(AABB("b",(5,0,0),(15,10,10)),AABB("a",(0,0,0),(10,10,10)),AABB("c",(20,0,0),(30,10,10)))
        self.assertEqual(broadphase_pairs(boxes),(("a","b"),))

if __name__=="__main__": unittest.main()
