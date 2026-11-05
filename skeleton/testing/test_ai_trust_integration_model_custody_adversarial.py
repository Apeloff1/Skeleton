"""Source chunks, model epochs and local routes reject unapproved divergence."""
import hashlib
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.artifact_stream import verify_chunks
from skeleton.ai.runtime.operational_ai.trust_gates.control.model_epoch import ModelEpoch
from skeleton.ai.runtime.operational_ai.trust_gates.control.local_router import LocalRouter

class ModelCustodyAdversarial(unittest.TestCase):
    def test_empty_artifact_is_refused(self):
        with self.assertRaises(GateViolation):
            verify_chunks(model_id="m",chunks=[],expected_digest="a"*64,
                expected_bytes=1,license="approved",source="local",approved=True)
    def test_mismatched_blob_refused_before_manifest_acceptance(self):
        raw=b"model"
        with self.assertRaises(GateViolation):
            verify_chunks(model_id="m",chunks=[raw],
                expected_digest=hashlib.sha256(b"other").hexdigest(),
                expected_bytes=len(raw),license="approved",source="local",approved=True)
    def test_epoch_compare_and_set_prevents_stale_swap(self):
        owner=ModelEpoch("a"*64,"a"*64)
        prior=owner.identity
        owner.swap("b"*64,"b"*64,approved=True)
        with self.assertRaises(GateViolation):
            owner.swap("c"*64,"c"*64,expected=prior,approved=True)
    def test_backend_unhealthy_fail_closed(self):
        router=LocalRouter()
        router.register("local",model_sha="a"*64,tokenizer_sha="b"*64)
        with self.assertRaises(GateViolation):
            router.admit(model_sha="a"*64,tokenizer_sha="b"*64)
        with self.assertRaises(GateViolation):
            router.admit(model_sha="c"*64,tokenizer_sha="b"*64)

if __name__=="__main__": unittest.main()
