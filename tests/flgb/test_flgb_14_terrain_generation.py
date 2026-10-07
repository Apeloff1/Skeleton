import unittest
from skeleton.game.generation.terrain_generation import TerrainChunk
D="a"*64
class T(unittest.TestCase):
 def test_chunk_identity(self):
  self.assertEqual(len(TerrainChunk("c",D,0,0,64,D,D).digest),64)
if __name__=="__main__": unittest.main()
