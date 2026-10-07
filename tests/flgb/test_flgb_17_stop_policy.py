import unittest
from skeleton.ai.forge.stop_policy import StopPolicy

class TestStopPolicy(unittest.TestCase):
    def test_all_stop_conditions_are_enforced(self):
        p=StopPolicy(100,1000,5,200000)
        self.assertFalse(p.should_stop(10,0,2000,100000))
        self.assertTrue(p.should_stop(100,0,2000,100000))
        self.assertTrue(p.should_stop(10,5,2000,100000))
        self.assertTrue(p.should_stop(10,0,500,100000))
        self.assertTrue(p.should_stop(10,0,2000,300000))

if __name__=="__main__": unittest.main()
