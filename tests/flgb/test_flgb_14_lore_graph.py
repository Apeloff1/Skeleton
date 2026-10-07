import unittest
from skeleton.game.generation.lore_graph import GenerationContractError, LoreEdge, LoreGraph, LoreNode
D="a"*64
E="b"*64
class TestLoreGraph(unittest.TestCase):
    def test_orphans_and_duplicate_edges_fail_closed(self):
        a=LoreNode("a",D,E,("history",))
        b=LoreNode("b",E,D,("place",))
        graph=LoreGraph((a,b),(LoreEdge("a","b","mentions"),))
        self.assertEqual(len(graph.digest),64)
        with self.assertRaises(GenerationContractError):
            LoreGraph((a,),(LoreEdge("a","missing","mentions"),))
if __name__=="__main__": unittest.main()
