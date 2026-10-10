import unittest
from skeleton.security.pii_handling import handle_pii

class TestPIIHandling(unittest.TestCase):
    def test_detected_pii_is_redacted_and_receipted(self):
        result=handle_pii("mail person@example.com or call +47 123 45 678")
        self.assertIn("[REDACTED:email]",result.redacted_text)
        self.assertTrue(result.findings)
        self.assertTrue(all(len(f.evidence_digest)==64 for f in result.findings))

if __name__=="__main__": unittest.main()
