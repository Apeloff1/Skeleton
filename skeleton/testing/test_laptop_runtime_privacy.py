"""Offline laptop runtime qualification: privacy; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.privacy import safe_record
from skeleton.ai.runtime.operational_ai.laptop_runtime.error_codes import public_error
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestPrivateOutput(unittest.TestCase):
    def test_prompt_bearer_and_private_path_are_dropped(self):
        result=safe_record({"status":"ok","bearer":"SECRET","prompt":"PRIVATE",
                            "private_path":"/home/owner/private","password":"TOKEN"})
        self.assertEqual(result,{"status":"ok"})
        self.assertNotIn("SECRET",str(result))
    def test_actual_exception_message_never_returned(self):
        result=public_error(RuntimeError("private prompt secret token filename"))
        self.assertNotIn("private",str(result))
        self.assertFalse(result["retry_automatic"])
    def test_public_operator_metadata_is_explicit(self):
        with self.assertRaises(ContractViolation):
            safe_record({"status":None})
        with self.assertRaises(ContractViolation):
            safe_record({"elapsed_ns":-1})

if __name__=="__main__":
    unittest.main()
