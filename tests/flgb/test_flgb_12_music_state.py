import unittest
from skeleton.game.presentation.music_state import MusicState
D="a"*64
class TestMusicState(unittest.TestCase):
    def test_transition_allowlist_is_explicit(self):
        state=MusicState("explore",D,120000,4,("combat","menu"))
        self.assertTrue(state.can_transition("combat"))
        self.assertFalse(state.can_transition("credits"))
if __name__=="__main__": unittest.main()
