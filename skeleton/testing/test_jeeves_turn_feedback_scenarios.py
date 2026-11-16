"""Exact-turn feedback and scenario-inventory regressions.

Synthetic receipts and generated fixtures below are test data, never evidence
of genuine local inference or competitive model performance.
"""
from hashlib import sha256
import json
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _digest_request
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.app.jeeves_approved_memory import MemoryRejected, MemoryConflict
from skeleton.app.jeeves_turn_feedback import TurnFeedback, inspect_shape
from skeleton.app.jeeves_chat_eval_scenarios import (
    build_suite, generated_case, inventory, long_dialogue,
)
from skeleton.app.offline_grounding import (
    prepare_evidence, grounded_request_digest, audit_answer_faithfulness,
)
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError
from skeleton.app.offline_web import HTML,JAVASCRIPT

MODEL="a"*64
TOKENIZER="b"*64


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.store=OfflineChatStore(":memory:")
        self.feedback=TurnFeedback(self.store,MODEL,TOKENIZER)
        self.sid=self.store.create(MODEL,TOKENIZER)

    def tearDown(self):
        self.store.close()

    def commit(self,question,answer,*,runtime_receipt=False,grounded=False):
        old=self.store.load(self.sid,MODEL,TOKENIZER)
        config=GenerationConfig(max_new_tokens=32)
        request_digest=_digest_request(question,config)
        evidence=None
        if grounded:
            request_digest=grounded_request_digest(request_digest)
            passage="The project has exactly thirteen verified components."
            source_hash=digest(passage)
            evidence=prepare_evidence(question,request_digest,[{
                "document_id":"fixture_doc","title":"Fixture",
                "document_sha256":source_hash,"chunk_index":0,
                "char_start":0,"char_end":len(passage),"passage":passage,
                "score":1.0,"citation":"local:fixture_doc:0:"+source_hash[:16],
            }],MODEL,TOKENIZER)
        transcript=old.transcript.append("user",question).append("assistant",answer)
        kwargs={"execution_receipt_digest":digest("test receipt "+str(old.revision))}
        result=self.store.commit(session=old,request_id="request_"+str(old.revision+1),
            request_digest=request_digest,transcript=transcript,text=answer,
            output_digest=digest(answer),prompt_tokens=10,generated_tokens=5,
            evidence_manifest=evidence,**(kwargs if runtime_receipt else {}))
        visible=audit_answer_faithfulness(answer,evidence)["published_text"] if evidence else answer
        return {"turn_revision":result.revision,"question_sha256":digest(question),
                "raw_answer_sha256":digest(answer),"visible_answer_sha256":digest(visible)}

    def save(self,pin,**overrides):
        params={"rating":"needs_improvement","flags":["incomplete","incorrect"],
                "note":"Check the omitted item.","expected_feedback_sha256":None,"approved":True}
        params.update(overrides)
        return self.feedback.save(self.sid,pin,**params)

    def test_exact_rating_lifecycle_and_cas(self):
        pin=self.commit("Name the requested deliverable.","An answer.",runtime_receipt=True)
        initial=self.feedback.inspect(self.sid,pin)
        self.assertIsNone(initial["feedback"])
        self.assertTrue(initial["can_prepare_followup"])
        self.assertIsNotNone(initial["local_execution_receipt_digest"])
        first=self.save(pin)
        self.assertEqual(first["version"],1)
        self.assertEqual(first["flags"],["incomplete","incorrect"])
        self.assertEqual(self.feedback.inspect(self.sid,pin)["feedback"],first)
        with self.assertRaises(MemoryConflict):
            self.save(pin)
        second=self.save(pin,expected_feedback_sha256=first["sha256"],rating="helpful",flags=[])
        self.assertEqual(second["version"],2)
        self.assertNotEqual(first["sha256"],second["sha256"])
        with self.assertRaises(MemoryConflict):
            self.feedback.delete(self.sid,pin,expected_feedback_sha256=first["sha256"],approved=True)
        out=self.feedback.delete(self.sid,pin,expected_feedback_sha256=second["sha256"],approved=True)
        self.assertTrue(out["previous_answer_unchanged"])
        self.assertIsNone(self.feedback.inspect(self.sid,pin)["feedback"])
        self.assertEqual(self.store.load(self.sid,MODEL,TOKENIZER).revision,1)

    def test_pin_rejects_changed_question_raw_and_visible(self):
        pin=self.commit("Question","Answer")
        for key in ("question_sha256","raw_answer_sha256","visible_answer_sha256"):
            with self.subTest(key=key),self.assertRaises(MemoryConflict):
                self.feedback.inspect(self.sid,{**pin,key:"0"*64})
        with self.assertRaises(MemoryRejected):
            self.feedback.inspect(self.sid,{**pin,"turn_revision":True})

    def test_explicit_approval_and_flags(self):
        pin=self.commit("Question","Answer")
        for changes in ({"approved":False},{"approved":1},{"rating":"excellent"},
                        {"flags":["incorrect","incorrect"]},{"flags":["unknown"]},
                        {"note":"é"*400},{"note":"\x00"}):
            with self.subTest(changes=changes),self.assertRaises(MemoryRejected):
                self.save(pin,**changes)
        self.assertIsNone(self.feedback.inspect(self.sid,pin)["feedback"])

    def test_historical_feedback_and_exact_latest_refinement(self):
        first=self.commit("First task","First answer")
        self.save(first)
        second=self.commit("Second task","Second answer")
        old=self.feedback.inspect(self.sid,first)
        self.assertFalse(old["can_prepare_followup"])
        self.assertIsNone(old["local_execution_receipt_digest"])
        with self.assertRaises(MemoryConflict):
            self.feedback.prepare_followup(self.sid,first,mode="refine",flags=[],note="")
        for mode in ("critique","refine","verify"):
            report=self.feedback.prepare_followup(self.sid,second,mode=mode,
                flags=["incomplete","unverified_actions"],note="Check all required outputs.")
            self.assertEqual(report["target"],second)
            self.assertIn("Check all required outputs.",report["draft"])
            self.assertEqual(report["draft_sha256"],digest(report["draft"]))
            self.assertTrue(report["requires_full_history"])
            self.assertFalse(report["automatic_send"])
            self.assertFalse(report["generation_performed"])
        self.assertEqual(self.store.load(self.sid,MODEL,TOKENIZER).revision,2)

    def test_grounded_visible_publication_not_raw_model_claim(self):
        pin=self.commit("What components are verified?",
                        "The project definitely has a million unrelated buildings.",grounded=True)
        report=self.feedback.inspect(self.sid,pin)
        self.assertEqual(report["target"],pin)
        if pin["visible_answer_sha256"]!=pin["raw_answer_sha256"]:
            with self.assertRaises(MemoryConflict):
                self.feedback.inspect(self.sid,{**pin,
                    "visible_answer_sha256":pin["raw_answer_sha256"]})
        self.save(pin)
        self.assertFalse(self.feedback.inspect(self.sid,pin)["semantic_quality_certified"])

    def test_summary_scope_and_cascade(self):
        pin=self.commit("Question","Answer")
        self.save(pin)
        summary=self.feedback.recent_summary()
        self.assertEqual(summary["reviewed_records"],1)
        self.assertEqual(summary["without_execution_receipt"],1)
        self.assertEqual(summary["flag_counts"]["incorrect"],1)
        self.assertFalse(summary["model_training_performed"])
        foreign=TurnFeedback(self.store,"c"*64,TOKENIZER)
        self.assertEqual(foreign.recent_summary()["reviewed_records"],0)
        self.store.delete(self.sid,MODEL,TOKENIZER)
        self.assertEqual(self.feedback.recent_summary()["reviewed_records"],0)

    def test_tamper_feedback_is_not_a_quality_pass(self):
        pin=self.commit("Question","Answer")
        self.save(pin)
        self.store._db.execute("UPDATE jeeves_turn_feedback SET note='tampered'")
        with self.assertRaises(MemoryRejected):
            self.feedback.inspect(self.sid,pin)
        self.assertEqual(self.feedback.recent_summary()["unavailable_records"],1)

    def test_dispatch_exact_feedback_controls(self):
        pin=self.commit("Question","Answer")
        app=OfflineHTTPApplication.__new__(OfflineHTTPApplication)
        app.turn_feedback=self.feedback
        path="/v1/sessions/"+self.sid+"/feedback-"
        status,report=app.dispatch("POST",path+"inspect",{"pin":pin})
        self.assertEqual(status,200)
        self.assertEqual(report["target"],pin)
        fields={"pin":pin,"rating":"helpful","flags":[],"note":"",
                "expected_feedback_sha256":None,"approved":True}
        status,row=app.dispatch("POST",path+"save",fields)
        self.assertEqual(status,200)
        with self.assertRaises(OfflineHTTPError) as caught:
            app.dispatch("POST",path+"save",fields)
        self.assertEqual(caught.exception.status,409)
        with self.assertRaises(OfflineHTTPError) as caught:
            app.dispatch("POST",path+"inspect",{"pin":pin,"tenant":"foreign"})
        self.assertEqual(caught.exception.status,400)
        self.assertEqual(app.dispatch("POST","/v1/feedback/summary",{})[1]["reviewed_records"],1)


class ShapeTests(unittest.TestCase):
    def test_explicit_word_limit_and_nonsemantic_status(self):
        report=inspect_shape("Answer in at most 3 words.","One two three four.")
        self.assertEqual(report["findings"][0]["id"],"word-budget")
        self.assertFalse(report["semantic_quality_certified"])
        self.assertEqual(inspect_shape("Explain word counts.","One two three.")["findings"],[])

    def test_json_shape_rejects_duplicate_keys_and_nonfinite(self):
        for answer in ('{"x":1,"x":2}','{"x":NaN}','Text {"x":1}'):
            self.assertEqual(inspect_shape("Return JSON only.",answer)["findings"][0]["id"],"json-shape")
        self.assertEqual(inspect_shape("Return JSON only.",'{"x":1}')["findings"],[])

    def test_action_claim_and_repetition_cues_are_not_verified(self):
        line="This is a long repeated line that deliberately exceeds forty characters."
        answer=line+"\n"+line+"\n"+line+"\nI uploaded the file."
        report=inspect_shape("Review the answer.",answer)
        self.assertEqual({x["id"] for x in report["findings"]},
                         {"repeated-long-lines","action-claim-cue"})
        self.assertTrue(report["human_review_required"])

    def test_unclosed_code_fence(self):
        fence=chr(96)*3
        self.assertTrue(inspect_shape("Code",fence+"python\nprint(1)")["findings"])
        self.assertEqual(inspect_shape("Code",fence+"python\nprint(1)\n"+fence)["findings"],[])


class ScenarioTests(unittest.TestCase):
    def test_all_families_and_seeded_determinism(self):
        suite=build_suite(seed=42,count=32,include_baseline=False)
        self.assertEqual(len(suite),32)
        self.assertEqual(inventory(suite),inventory(build_suite(seed=42,count=32,include_baseline=False)))
        self.assertNotEqual(inventory(suite)["suite_sha256"],
                            inventory(build_suite(seed=43,count=32,include_baseline=False))["suite_sha256"])
        self.assertGreaterEqual(len({x.category for x in suite}),8)
        self.assertEqual(len({x.case_id for x in suite}),32)
        for case in suite:
            case.validate()

    def test_shards_match_whole_case_identity(self):
        full=build_suite(seed=7,start=0,count=48,include_baseline=False)
        a=build_suite(seed=7,start=0,count=17,include_baseline=False)
        b=build_suite(seed=7,start=17,count=31,include_baseline=False)
        self.assertEqual(full,a+b)
        self.assertEqual(full[19].fingerprint(),generated_case(7,19).fingerprint())

    def test_thousand_turns_has_genuinely_distant_final_recall(self):
        case=long_dialogue(2026,1000)
        case.validate()
        self.assertEqual(len(case.turns),1000)
        first=case.turns[0].prompt
        final=case.turns[-1]
        self.assertIn(final.exact_answer,first)
        self.assertTrue(all(final.exact_answer not in turn.prompt for turn in case.turns[1:-1]))
        report=inventory((case,))
        self.assertEqual(report["max_dialogue_turns"],1000)
        self.assertFalse(report["generation_performed"])
        self.assertFalse(report["semantic_quality_certified"])

    def test_invalid_bounds_and_empty_suite(self):
        for options in ({"seed":True},{"start":24999,"count":2},
                        {"include_baseline":False,"count":0},
                        {"count":25000},{"long_turns":1001},{"long_turns":True}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                build_suite(**options)

    def test_workspace_has_actual_controls_and_routes(self):
        for id in ("adaptive-context-panel","adaptive-plan","adaptive-apply","adaptive-send",
                   "memory-vector-status","memory-vector-start","memory-vector-more",
                   "quality-dialog","quality-save","quality-critique","quality-refine","quality-verify"):
            self.assertEqual(HTML.count('id="'+id+'"'),1)
        for route in ("/adaptive-context","/v1/memory-vector/refresh","/feedback-followup",
                      "/feedback-save","/feedback-inspect"):
            self.assertIn(route,JAVASCRIPT)
        self.assertIn("if(andSend) await submit(false);",JAVASCRIPT)


if __name__=="__main__":
    unittest.main()
