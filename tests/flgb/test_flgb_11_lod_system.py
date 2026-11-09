import unittest
from skeleton.game.render.lod_system import LODLevel, LODPolicy, RenderContractError
D="a"*64
E="b"*64
F="c"*64

class TestLOD(unittest.TestCase):
    def test_distance_thresholds_are_contiguous_and_monotonic(self):
        policy=LODPolicy((LODLevel(0,0,D),LODLevel(1,1000,E),LODLevel(2,5000,F)))
        self.assertEqual(policy.choose(4999).level,1)
        self.assertEqual(policy.choose(5000).level,2)
        with self.assertRaises(RenderContractError):
            LODPolicy((LODLevel(0,100,D),LODLevel(2,200,E)))

if __name__=="__main__": unittest.main()
