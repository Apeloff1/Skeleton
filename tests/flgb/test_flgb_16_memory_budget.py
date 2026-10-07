import unittest
from skeleton.game.build.memory_budget import MemoryBudget
class T(unittest.TestCase):
 def test_reserve(self): self.assertEqual(MemoryBudget("gpu",1000,100).available(800),100)
if __name__=="__main__": unittest.main()
