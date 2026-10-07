import unittest
from skeleton.game.presentation.audio_graph import AudioGraph, AudioNode, PresentationContractError
D="a"*64
class TestAudioGraph(unittest.TestCase):
    def test_audio_graph_is_acyclic(self):
        g=AudioGraph((AudioNode("src","sample",(),D),AudioNode("out","mix",("src",),D)),"out")
        self.assertEqual(len(g.digest),64)
        with self.assertRaises(PresentationContractError):
            AudioGraph((AudioNode("a","x",("b",),D),AudioNode("b","x",("a",),D)),"a")
if __name__=="__main__": unittest.main()
