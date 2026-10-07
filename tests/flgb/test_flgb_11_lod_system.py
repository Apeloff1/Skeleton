import unittest
from skeleton.game.render.lod_system import LODLevel, RenderContractError, select_lod
D="a"*64
E="b"*64
F="c"*64

class TestLOD(unittest.TestCase):
    def test_lod_boundaries_are_deterministic(self):
        levels=(LODLevel(0,0,D),LODLevel(1,100,E),LODLevel(2,500,F))
        self.assertEqual(select_lod(levels,99).level,0)
        self.assertEqual(select_lod(levels,100).level,1)
        with self.assertRaises(RenderContractError):
            select_lod((LODLevel(1,100,E),),100)

if __name__=="__main__": unittest.main()
