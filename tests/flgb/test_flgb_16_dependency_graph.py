import unittest
from skeleton.game.build.dependency_graph import BuildContractError, BuildNode, DependencyGraph
D="a"*64
class T(unittest.TestCase):
 def test_topology_and_cycle(self):
  g=DependencyGraph((BuildNode("a",D,()),BuildNode("b",D,("a",)))); self.assertEqual(g.order,("a","b"))
  with self.assertRaises(BuildContractError): DependencyGraph((BuildNode("a",D,("b",)),BuildNode("b",D,("a",))))
if __name__=="__main__": unittest.main()
