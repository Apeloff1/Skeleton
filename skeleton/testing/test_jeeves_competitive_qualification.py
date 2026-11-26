"""Synthetic custody fixtures only; no pretrained performance claims."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore,_digest_request
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.app.local_ai import _strict_context_digest
from skeleton.app.jeeves_chat_quality import Case,TurnSpec,qualify,_hash,_stable
from skeleton.app.jeeves_chat_eval_scenarios import inventory
from skeleton.app.jeeves_competitive_qualification import (
    CompetitiveRejected,audit_database,compare_audited,blind_package,validate_capture,
)

TOKENIZER="b"*64
CASES=(
    Case("reasoning.a","reasoning",(TurnSpec("Give the number 2.",exact_answer="2"),)),
    Case("dialogue.b","dialogue",(TurnSpec("Describe a garden.",human_rubric="Relevant and concrete."),
         TurnSpec("Now give just 7.",exact_answer="7"))),
)
PROTOCOL={"schema":"skeleton.jeeves.local-benchmark-protocol.v1","max_output_tokens":32,
          "require_full_history":True,"grounded":False,"one_clean_session_per_case":True,
          "system_prompt":None,"retries":0}


def fixture(database,model,answers):
    store=OfflineChatStore(database)
    captures=[];custody=[];sessions=[]
    protocol=_hash(_stable(PROTOCOL))
    try:
        for case in CASES:
            sid=store.create(model,TOKENIZER)
            sessions.append({"case_id":case.case_id,"session_id":sid})
            for index,turn in enumerate(case.turns):
                answer=answers[(case.case_id,index)]
                rid="fixture-"+case.case_id.replace(".","-")+"-"+str(index)
                saved=store.load(sid,model,TOKENIZER)
                output=_hash(answer)
                execution=_hash(model+rid)
                req=_strict_context_digest(_digest_request(turn.prompt,GenerationConfig(max_new_tokens=32)),True)
                store.commit(session=saved,request_id=rid,request_digest=req,
                    transcript=saved.transcript.append("user",turn.prompt).append("assistant",answer),
                    text=answer,output_digest=output,prompt_tokens=16,generated_tokens=2,
                    execution_receipt_digest=execution)
                captures.append({"case_id":case.case_id,"case_sha256":case.fingerprint(),
                    "turn_index":index,"prompt_sha256":_hash(turn.prompt),"model_digest":model,
                    "protocol_digest":protocol,"answer":answer,"answer_sha256":output,
                    "execution_receipt_digest":execution})
                custody.append({"case_id":case.case_id,"turn_index":index,"session_id":sid,
                    "request_id":rid,"revision":index+1,"input_tokens":16,"output_tokens":2,
                    "elapsed_ns":100000000,"answer_sha256":output,"execution_receipt_digest":execution})
    finally:
        store.close()
    return {"schema":"skeleton.jeeves.local-benchmark-capture.v1","model_digest":model,
            "tokenizer_digest":TOKENIZER,"protocol_digest":protocol,"protocol_descriptor":PROTOCOL,
            "suite_inventory":inventory(CASES),"sessions":sessions,"captures":captures,"turn_custody":custody,
            "report":qualify(CASES,captures,model_digest=model,protocol_digest=protocol),
            "live_endpoint_observed":True,"independent_receipt_verification":False}


class CompetitiveQualificationTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.left_db=Path(self.root.name)/"left.sqlite3"
        self.right_db=Path(self.root.name)/"right.sqlite3"
        self.left=fixture(self.left_db,"a"*64,{("reasoning.a",0):"2",("dialogue.b",0):"Flowers.",("dialogue.b",1):"7"})
        self.right=fixture(self.right_db,"c"*64,{("reasoning.a",0):"3",("dialogue.b",0):"A concrete garden.",("dialogue.b",1):"7"})

    def test_exact_readonly_database_and_reproduced_scoring(self):
        result=audit_database(CASES,self.left,self.left_db)
        self.assertEqual(result["verified_turn_count"],3)
        self.assertTrue(result["read_only_sqlite_custody_verified"])
        self.assertFalse(result["independent_physical_inference_attestation"])
        self.assertFalse(result["semantic_quality_certified"])

    def test_paired_distinct_model_comparison_discloses_limits(self):
        report=compare_audited(CASES,self.left,self.right,self.left_db,self.right_db)
        self.assertEqual(report["case_level_outcomes"],{"both_pass":1,"left_only":1,
            "right_only":0,"both_fail":0,"unscored":0})
        self.assertEqual(report["left_measurements"]["turns"],3)
        self.assertFalse(report["general_competitive_superiority_certified"])
        self.assertFalse(report["human_semantic_review_complete"])
        self.assertFalse(report["model_promotion_authorized"])
        self.assertEqual(report["paired_case_exact_two_sided_p"],1.0)
        with self.assertRaises(CompetitiveRejected):
            compare_audited(CASES,self.left,self.left,self.left_db,self.right_db)

    def test_tampered_capture_and_forged_score_rejected(self):
        wrong=copy.deepcopy(self.left)
        wrong["captures"][0]["answer"]="4"
        wrong["captures"][0]["answer_sha256"]=_hash("4")
        wrong["turn_custody"][0]["answer_sha256"]=_hash("4")
        wrong["report"]=qualify(CASES,wrong["captures"],model_digest=wrong["model_digest"],
                                protocol_digest=wrong["protocol_digest"])
        with self.assertRaises(CompetitiveRejected):
            audit_database(CASES,wrong,self.left_db)

    def test_missing_or_reused_custody_rejected(self):
        for change in ("missing","duplicate","mismatched"):
            wrong=copy.deepcopy(self.left)
            if change=="missing":wrong["turn_custody"].pop()
            elif change=="duplicate":wrong["turn_custody"][1]["request_id"]=wrong["turn_custody"][0]["request_id"]
            else:wrong["turn_custody"][0]["elapsed_ns"]=True
            with self.subTest(change=change),self.assertRaises(CompetitiveRejected):
                validate_capture(CASES,wrong)

    def test_blind_review_separates_public_items_and_model_map(self):
        public,private=blind_package(CASES,self.left,self.right)
        self.assertEqual(len(public["items"]),1)
        card=public["items"][0]
        self.assertEqual({card["answer_a"],card["answer_b"]},{"Flowers.","A concrete garden."})
        self.assertNotIn("a_model_digest",card)
        self.assertEqual(private["package_sha256"],public["sha256"])
        self.assertEqual(private["mapping"][0]["review_id"],card["review_id"])


if __name__=="__main__":
    unittest.main()
