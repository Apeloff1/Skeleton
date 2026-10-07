import unittest
from skeleton.game.presentation.controller_support import ControllerDescriptor
class TestControllerSupport(unittest.TestCase):
    def test_capability_query_is_explicit(self):
        c=ControllerDescriptor("c","v","p",("haptics","gyro"))
        self.assertTrue(c.supports("gyro"))
        self.assertFalse(c.supports("touchpad"))
if __name__=="__main__":unittest.main()
