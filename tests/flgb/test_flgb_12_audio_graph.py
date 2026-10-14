import unittest
from skeleton.game.presentation.audio_graph import AudioGraph, AudioNode, PresentationContractError
D="a"*64

class TestAudioGraph(unittest.TestCase):
    def test_all_audio_nodes_are_cycle_checked(self):
        graph=AudioGraph((AudioNode("src","sample",(),D),AudioNode("out","mix",("src",),D)),"out")
        self.assertEqual(len(graph.digest),64)
        with self.assertRaises(PresentationContractError):
            AudioGraph((AudioNode("a","fx",("b",),D),AudioNode("b","fx",("a",),D),AudioNode("out","mix",(),D)),"out")

if __name__=="__main__": unittest.main()
