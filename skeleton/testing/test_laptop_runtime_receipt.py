"""Offline laptop runtime qualification: receipt; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import MODEL,TOKENIZER,OUTPUT_SHA,FakeWorker
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestNativeReceipt(unittest.TestCase):
    def setUp(self):
        worker=FakeWorker()
        sid="s_1";worker.spine.create(sid)
        self.value=worker.turn(sid,"r_1","hi")
    def verify(self,value):
        return verify_turn_receipt(value,model_sha256=MODEL,tokenizer_sha256=TOKENIZER)
    def test_model_digest_matches_original_committed_text(self):
        self.assertEqual(self.verify(self.value)["output_sha256"],OUTPUT_SHA)
    def test_mutations_do_not_pass_as_native_receipts(self):
        for field,bad in (("text","tampered"),("output_sha256","a"*64),
                          ("model_sha256","b"*64),("tokenizer_sha256","a"*64),
                          ("prompt_tokens",-1),("generated_tokens",9000),
                          ("replayed","false")):
            with self.subTest(field=field):
                with self.assertRaises(ContractViolation):
                    self.verify({**self.value,field:bad})

if __name__=="__main__":
    unittest.main()
