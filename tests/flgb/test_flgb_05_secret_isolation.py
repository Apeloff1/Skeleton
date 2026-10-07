import unittest
from skeleton.security.secret_isolation import isolate_secrets
class TestSecrets(unittest.TestCase):
    def test_secret_material_is_redacted(self):
        result=isolate_secrets("api_key=abcdefghijklmnop")
        self.assertFalse(result.clean)
        self.assertIn("[REDACTED:secret]",result.redacted_text)
        self.assertNotIn("abcdefghijklmnop",result.redacted_text)
if __name__=="__main__": unittest.main()
