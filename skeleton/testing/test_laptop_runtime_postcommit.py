"""Offline laptop runtime qualification: postcommit; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,OUTPUT_SHA
from skeleton.ai.runtime.operational_ai.laptop_runtime.postcommit_stream import chunks
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestPostcommit(unittest.TestCase):
    def setUp(self):
        self.receipt={"text":"hello","output_sha256":OUTPUT_SHA,"replayed":False}
    def test_original_bytes_roundtrip_from_committed_text(self):
        stream=chunks(self.receipt,chunk_bytes=2,max_chunks=8)
        self.assertEqual(stream["mode"],"postcommit-not-native-stream")
        self.assertEqual("".join(f["text"] for f in stream["frames"]),"hello")
        self.assertEqual(stream["total_bytes"],5)
    def test_changed_output_cannot_be_repackaged(self):
        for text in ("other","HELLO","hi"):
            with self.subTest(text=text):
                with self.assertRaises(ContractViolation):
                    chunks({**self.receipt,"text":text})
    def test_bounded_chunks_refuse_unbounded_frames(self):
        with self.assertRaises(ContractViolation):
            chunks(self.receipt,chunk_bytes=1,max_chunks=1)

if __name__=="__main__":
    unittest.main()
