import unittest
from skeleton.game.presentation.input_mapping import InputBinding, InputMap, PresentationContractError
class TestInputMapping(unittest.TestCase):
    def test_same_chord_cannot_map_to_two_actions(self):
        a=InputBinding("a","jump","keyboard","Space",())
        InputMap((a,))
        with self.assertRaises(PresentationContractError):
            InputMap((a,InputBinding("b","fire","keyboard","Space",())))
if __name__=="__main__": unittest.main()
