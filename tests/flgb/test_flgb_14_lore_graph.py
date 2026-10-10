import unittest
from skeleton.game.generation.lore_graph import ContinuityContractError, LoreClaim, LoreEdge, LoreGraph
D="a"*64
E="b"*64

class TestLoreGraph(unittest.TestCase):
    def test_edges_must_reference_known_distinct_claims(self):
        claims=(LoreClaim("a","hero","born-in",D,E),LoreClaim("b","hero","served",E,D))
        graph=LoreGraph(claims,(LoreEdge("a","b","precedes"),))
        self.assertEqual(len(graph.digest),64)
        with self.assertRaises(ContinuityContractError):
            LoreGraph(claims,(LoreEdge("a","missing","supports"),))

if __name__=="__main__": unittest.main()
