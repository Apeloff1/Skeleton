import unittest
from skeleton.game.build.dependency_graph import BuildNode, DependencyGraph
from skeleton.game.build.incremental_build import incremental_rebuild
D="a"*64
class T(unittest.TestCase):
 def test_transitive_invalidation(self):
  g=DependencyGraph((BuildNode("a",D,()),BuildNode("b",D,("a",)),BuildNode("c",D,("b",))))
  self.assertEqual(incremental_rebuild(g,("a",)),("a","b","c"))
if __name__=="__main__": unittest.main()
