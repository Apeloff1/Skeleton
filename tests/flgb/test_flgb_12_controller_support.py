import unittest
from skeleton.game.presentation.controller_support import ControllerProfile

class TestControllerSupport(unittest.TestCase):
    def test_control_capabilities_are_explicit(self):
        profile=ControllerProfile("pad",1118,654,("a","b","left-stick"),True)
        self.assertTrue(profile.supports("a"))
        self.assertFalse(profile.supports("gyro"))

if __name__=="__main__": unittest.main()
