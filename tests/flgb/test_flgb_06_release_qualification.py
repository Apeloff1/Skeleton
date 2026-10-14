import unittest
from skeleton.ai.assurance.release_qualification import QualificationGate, ReleaseQualification
D="a"*64

class TestReleaseQualification(unittest.TestCase):
    def test_any_failed_gate_blocks_release(self):
        ok=QualificationGate("unit",True,False,D)
        critical=QualificationGate("security",False,True,D)
        qualification=ReleaseQualification(D,D,(ok,critical),"independent")
        self.assertFalse(qualification.qualified)
        passed=ReleaseQualification(D,D,(ok,QualificationGate("security",True,True,D)),"independent")
        self.assertTrue(passed.qualified)

if __name__=="__main__": unittest.main()
