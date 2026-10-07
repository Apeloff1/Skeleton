import unittest
from skeleton.game.generation.continuity_verifier import ContinuityFinding, ContinuityReport
D="a"*64
class TestContinuityVerifier(unittest.TestCase):
    def test_error_or_critical_blocks_report(self):
        ok=ContinuityReport(D,(ContinuityFinding("w","minor","warning",D),))
        bad=ContinuityReport(D,(ContinuityFinding("e","canon","error",D),))
        self.assertTrue(ok.passed)
        self.assertFalse(bad.passed)
        self.assertNotEqual(ok.digest,bad.digest)
if __name__=="__main__": unittest.main()
