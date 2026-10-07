import unittest
from skeleton.game.presentation.music_state import MusicState, MusicTransition, PresentationContractError, next_music_state
D="a"*64
class TestMusicState(unittest.TestCase):
    def test_music_transition_is_event_deterministic(self):
        states=(MusicState("calm",D,200000),MusicState("fight",D,900000))
        transitions=(MusicTransition("calm","combat","fight",500),)
        self.assertEqual(next_music_state("calm","combat",states,transitions),"fight")
        with self.assertRaises(PresentationContractError):
            next_music_state("calm","combat",states,transitions+transitions)
if __name__=="__main__":unittest.main()
