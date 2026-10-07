import unittest
from skeleton.game.presentation.audio_graph import AudioNode, PresentationContractError, validate_audio_graph
D="a"*64
class TestAudioGraph(unittest.TestCase):
    def test_audio_graph_is_acyclic(self):
        nodes=(AudioNode("src","clip",(),D),AudioNode("out","mixer",("src",),D))
        self.assertEqual([n.node_id for n in validate_audio_graph(nodes,"out")],["out","src"])
        with self.assertRaises(PresentationContractError):
            validate_audio_graph((AudioNode("a","x",("b",),D),AudioNode("b","x",("a",),D)),"a")
if __name__=="__main__":unittest.main()
