import unittest
from skeleton.game.presentation.input_mapping import InputBinding, InputMap, PresentationContractError

class TestInputMapping(unittest.TestCase):
    def test_ambiguous_chords_are_rejected(self):
        mapping=InputMap((InputBinding("jump-kb","jump","keyboard","space"),InputBinding("jump-pad","jump","gamepad","a")))
        self.assertEqual(mapping.actions_for_device("gamepad"),("jump",))
        with self.assertRaises(PresentationContractError):
            InputMap((InputBinding("a","jump","keyboard","space"),InputBinding("b","fire","keyboard","space")))

if __name__=="__main__": unittest.main()
