"""Capture-shard verification fixtures; no live model or benchmark score."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.app.jeeves_chat_quality import Case, TurnSpec, QualificationRejected, qualify, compare
from skeleton.app.jeeves_chat_eval_scenarios import inventory
from skeleton.app.jeeves_chat_eval_aggregate import aggregate_shards

MODEL="a"*64
TOKENIZER="b"*64
PROTOCOL="c"*64


def digest(text):
    return sha256(text.encode()).hexdigest()


def fixture(cases,*,model=MODEL,protocol=PROTOCOL,tokenizer=TOKENIZER):
    captures=[]
    for case in cases:
        for index,turn in enumerate(case.turns):
            answer=turn.exact_answer or "fixture answer"
            captures.append({"case_id":case.case_id,"case_sha256":case.fingerprint(),
                "turn_index":index,"prompt_sha256":digest(turn.prompt),
                "model_digest":model,"protocol_digest":protocol,"answer":answer,
                "answer_sha256":digest(answer),
                "execution_receipt_digest":digest(model+case.case_id+str(index))})
    report=qualify(cases,captures,model_digest=model,protocol_digest=protocol)
    # This is deliberately synthetic input to test validation and rescoring.
    # A real capture must be collected from the authenticated endpoint.
    return {"schema":"skeleton.jeeves.local-benchmark-capture.v1",
            "model_digest":model,"tokenizer_digest":tokenizer,"protocol_digest":protocol,
            "suite_inventory":inventory(cases),"captures":captures,"report":report,
            "live_endpoint_observed":True,"independent_receipt_verification":False}


class ShardTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory()
        self.path=Path(self.root.name)
        self.a=Case("test.a","memory",(TurnSpec("Say alpha",exact_answer="alpha"),))
        self.b=Case("test.b","instruction",(TurnSpec("Say beta",exact_answer="beta"),
                                            TurnSpec("Say gamma",exact_answer="gamma")))
        self.cases=(self.a,self.b)

    def tearDown(self):
        self.root.cleanup()

    def write(self,name,data):
        path=self.path/name
        path.write_text(json.dumps(data),encoding="utf-8")
        return path

    def test_aggregate_matches_expected_whole_suite(self):
        a=self.write("a.json",fixture((self.a,)))
        b=self.write("b.json",fixture((self.b,)))
        result=aggregate_shards(self.cases,[a,b])
        self.assertEqual(result,aggregate_shards(self.cases,[b,a]))
        self.assertEqual(result["cases"],2)
        self.assertEqual(result["turns"],3)
        self.assertEqual(result["suite_sha256"],inventory(self.cases)["suite_sha256"])
        self.assertTrue(result["source_shards_rescored"])
        self.assertFalse(result["semantic_quality_certified"])
        self.assertFalse(result["external_receipts_independently_verified"])
        self.assertEqual(compare(result,result)["categories"]["memory"]["delta_percentage_points"],0)

    def test_reject_duplicate_missing_overlap_and_foreign_shards(self):
        a=self.write("a.json",fixture((self.a,)))
        b=self.write("b.json",fixture((self.b,)))
        wrong=self.write("wrong.json",fixture((self.b,),model="d"*64))
        wrong_protocol=self.write("wrong-protocol.json",fixture((self.b,),protocol="e"*64))
        wrong_tokenizer=self.write("wrong-tokenizer.json",fixture((self.b,),tokenizer="f"*64))
        overlap=self.write("overlap.json",fixture(self.cases))
        for paths in ([a],[a,a],[a,wrong],[a,wrong_protocol],[a,wrong_tokenizer],[a,overlap],[]):
            with self.subTest(paths=paths),self.assertRaises(QualificationRejected):
                aggregate_shards(self.cases,paths)
        self.assertEqual(aggregate_shards(self.cases,[a,b])["turns"],3)

    def test_rescore_instead_of_trusting_report(self):
        a=self.write("a.json",fixture((self.a,)))
        bad=fixture((self.b,))
        bad["captures"][0]["answer"]="wrong"
        bad["captures"][0]["answer_sha256"]=digest("wrong")
        b=self.write("b.json",bad)
        with self.assertRaises(QualificationRejected):
            aggregate_shards(self.cases,[a,b])

    def test_reject_reused_execution_receipt_across_shards(self):
        left=fixture((self.a,))
        right=fixture((self.b,))
        right["captures"][0]["execution_receipt_digest"]=left["captures"][0]["execution_receipt_digest"]
        right["report"]=qualify((self.b,),right["captures"],model_digest=MODEL,protocol_digest=PROTOCOL)
        a=self.write("a.json",left);b=self.write("b.json",right)
        with self.assertRaises(QualificationRejected):
            aggregate_shards(self.cases,[a,b])


if __name__=="__main__":
    unittest.main()
