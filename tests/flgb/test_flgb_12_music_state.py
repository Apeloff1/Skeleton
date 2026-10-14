import unittest
from skeleton.game.presentation.music_state import MusicState
D="a"*64
E="b"*64

class TestMusicState(unittest.TestCase):
    def test_bar_boundary_is_integer_quantized(self):
        state=MusicState("combat",(D,E),120000,4)
        self.assertEqual(state.next_bar_boundary_ms(1),2000)
        self.assertEqual(state.next_bar_boundary_ms(2000),2000)
        self.assertEqual(state.next_bar_boundary_ms(2001),4000)

if __name__=="__main__": unittest.main()
