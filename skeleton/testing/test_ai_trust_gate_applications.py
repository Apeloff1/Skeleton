"""Cross-system composed operational AI adapter checks, no mock-model claims."""
import hashlib
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.artifact_stream import verify_chunks
from skeleton.ai.runtime.operational_ai.trust_gates.applications.retrieval_spans import verify_excerpt
from skeleton.ai.runtime.operational_ai.trust_gates.applications.stream_receipts import StreamAssembler
from skeleton.ai.runtime.operational_ai.trust_gates.applications.quota_book import QuotaBook
from skeleton.ai.runtime.operational_ai.trust_gates.applications.context_history import prepare_history
from skeleton.ai.runtime.operational_ai.trust_gates.applications.journal_chain import journal_digest,verify_chain
from skeleton.ai.runtime.operational_ai.trust_gates.applications.transport_envelope import inspect_request
from skeleton.ai.runtime.operational_ai.trust_gates.applications.admission_probe import inspect_admission
from skeleton.ai.runtime.operational_ai.trust_gates.applications.checkpoint_probe import inspect_checkpoint

class Applications(unittest.TestCase):
    def test_actual_streaming_source_hash(self):
        raw=b"abc"
        receipt=verify_chunks(model_id="model",chunks=[b"a",b"bc"],
            expected_digest=hashlib.sha256(raw).hexdigest(),expected_bytes=3,
            license="approved-license",source="local-manifest",approved=True)
        self.assertEqual(receipt["status"],"accepted")
        with self.assertRaises(GateViolation):
            verify_chunks(model_id="model",chunks=[raw],expected_digest="a"*64,
                expected_bytes=3,license="approved-license",source="local-manifest",approved=True)
    def test_byte_accurate_utf8_retrieval(self):
        self.assertEqual(verify_excerpt("doc",b"ab",0,1,approved=True)["status"],"accepted")
        with self.assertRaises(GateViolation):
            verify_excerpt("doc","☃".encode(),0,1,approved=True)
    def test_stream_closes_to_double_finish(self):
        stream=StreamAssembler("r",max_bytes=16,token_ceiling=5)
        stream.append("a");stream.append("b")
        self.assertEqual(stream.finish(generated_tokens=2)["text"],"ab")
        with self.assertRaises(GateViolation): stream.finish(generated_tokens=2)
    def test_quota_reservation_release_and_actual_charge(self):
        book=QuotaBook(tenant_ceiling=50,global_ceiling=100)
        book.reserve("tenant","r",prompt_tokens=10,output_tokens=10)
        self.assertEqual(book.commit("tenant","r",actual_prompt=5,actual_output=2)["charged_tokens"],7)
        with self.assertRaises(GateViolation): book.release("tenant","r")
    def test_context_turns_must_alternate(self):
        accepted=prepare_history("chat",[{"role":"user","content":"hello"},
            {"role":"assistant","content":"hi"}],"next",revision=2)
        self.assertEqual(accepted["messages"][-1]["content"],"next")
        with self.assertRaises(GateViolation):
            prepare_history("chat",[{"role":"assistant","content":"bad"}],"next")
    def test_canonical_journal_content_hash_recalculated(self):
        z="0"*64
        event={"stream":"chat","sequence":1,"epoch":1,"kind":"inference.completed",
               "payload_sha":"a"*64,"prev_sha":z}
        event["event_sha"]=journal_digest(**event)
        self.assertEqual(verify_chain([event],stream="chat",epoch=1)["events"],1)
        event["payload_sha"]="b"*64
        with self.assertRaises(GateViolation): verify_chain([event],stream="chat",epoch=1)
    def test_transport_envelope_binds_loopback(self):
        self.assertEqual(inspect_request(host="127.0.0.1",method="POST",auth_type="bearer",
                          bearer="X"*64,body=b"{}")["status"],"accepted")
        with self.assertRaises(GateViolation):
            inspect_request(host="0.0.0.0",method="POST",auth_type="bearer",
                            bearer="X"*64,body=b"{}")
    def test_actual_monotonic_deadline(self):
        self.assertEqual(inspect_admission(tenant="t",deadline_ns=20,queue_depth=0,
             queue_ceiling=10,requested_tokens=4,token_ceiling=10,clock=lambda:10)["status"],"accepted")
        with self.assertRaises(GateViolation):
            inspect_admission(tenant="t",deadline_ns=10,queue_depth=0,
                queue_ceiling=10,requested_tokens=4,token_ceiling=10,clock=lambda:10)
    def test_checkpoint_requires_explicit_owner_approval(self):
        manifest={"model_id":"x","model_sha":"a"*64,"tokenizer_sha":"a"*64,
                  "format":"gguf-v3","bytes":100,"step":1}
        with self.assertRaises(GateViolation): inspect_checkpoint(manifest)
        self.assertEqual(inspect_checkpoint(manifest,operator_approval=True)["status"],"accepted")

if __name__=="__main__": unittest.main()
