import unittest
from skeleton.game.presentation.input_mapping import InputBinding, PresentationContractError, validate_input_map
class TestInputMapping(unittest.TestCase):
    def test_physical_control_cannot_be_ambiguous(self):
        bindings=(InputBinding("jump","keyboard","space"),InputBinding("jump","gamepad","south"))
        self.assertEqual(len(validate_input_map(bindings)),2)
        with self.assertRaises(PresentationContractError):
            validate_input_map((InputBinding("jump","keyboard","space"),InputBinding("fire","keyboard","space")))
if __name__=="__main__":unittest.main()
