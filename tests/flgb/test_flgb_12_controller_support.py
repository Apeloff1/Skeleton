import unittest
from skeleton.game.presentation.controller_support import ControllerProfile
class TestController(unittest.TestCase):
    def test_capabilities_are_explicit(self):
        p=ControllerProfile("pad",1,2,("a","b","lx"),True)
        self.assertTrue(p.supports("a"))
        self.assertFalse(p.supports("gyro"))
if __name__=="__main__": unittest.main()
