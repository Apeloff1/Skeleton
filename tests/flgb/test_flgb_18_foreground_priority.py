import unittest
from skeleton.ai.product.foreground_priority import ForegroundPolicy, ResourceRequest

class TestForegroundPriority(unittest.TestCase):
    def test_only_preemptible_background_is_preempted(self):
        policy=ForegroundPolicy("p",2,2,True)
        preemptible=ResourceRequest("bg",1,1,0,False,True)
        fixed=ResourceRequest("fixed",1,1,0,False,False)
        foreground=ResourceRequest("fg",1,1,0,True,False)
        self.assertTrue(policy.should_preempt(True,preemptible))
        self.assertFalse(policy.should_preempt(True,fixed))
        self.assertFalse(policy.should_preempt(True,foreground))

if __name__=="__main__": unittest.main()
