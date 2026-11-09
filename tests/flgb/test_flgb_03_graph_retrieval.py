import unittest
from skeleton.ai.context.graph_retrieval import GraphEdge, graph_retrieve
class TestGraphRetrieval(unittest.TestCase):
    def test_bounded_bfs(self):
        edges=(GraphEdge("a","b","dep"),GraphEdge("b","c","dep"),GraphEdge("a","d","dep"))
        self.assertEqual(graph_retrieve(("a",),edges,max_hops=1,max_results=10),("a","b","d"))
        self.assertEqual(graph_retrieve(("a",),edges,max_hops=2,max_results=10),("a","b","d","c"))
if __name__=="__main__": unittest.main()
