import unittest
from skeleton.game.presentation.haptics import HapticPoint, PresentationContractError, validate_haptic_envelope
class TestHaptics(unittest.TestCase):
    def test_envelope_times_strictly_increase(self):
        points=(HapticPoint(0,0),HapticPoint(10,1000000),HapticPoint(20,0))
        self.assertEqual(validate_haptic_envelope(points),points)
        with self.assertRaises(PresentationContractError):validate_haptic_envelope((HapticPoint(10,1),HapticPoint(10,2)))
if __name__=="__main__":unittest.main()
