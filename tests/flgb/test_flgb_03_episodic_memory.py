import unittest
from skeleton.ai.context.episodic_memory import EpisodicMemory
D="a"*64
E="b"*64
class TestEpisodicMemory(unittest.TestCase):
    def test_hash_chain_is_deterministic(self):
        memory=EpisodicMemory().append("e0",D,E).append("e1",E,D)
        self.assertEqual(memory.episodes[1].prior_episode_digest,memory.episodes[0].digest)
        self.assertEqual(len(memory.digest),64)
if __name__=="__main__": unittest.main()
