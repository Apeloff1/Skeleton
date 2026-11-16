"""CPU-portable contract regressions.

Scripted responses below are intentionally synthetic fixtures. A passing test
does not attest pretrained weights or a physical multimodal execution.
"""
from __future__ import annotations

import asyncio
import base64
import copy
from fractions import Fraction
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import wave

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore,_digest_request
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.app.jeeves_native_peer import (
    NativePeer,PeerSpec,PeerRejected,digest,stable,strict_json,_validate_messages,
)
from skeleton.app.jeeves_native_multimodal import analyze,audio_part,_raw_media
from skeleton.app.jeeves_semantic_compression import (
    CompressionPolicy,partition,make_plan,compress,review_result,
)
from skeleton.app.jeeves_independent_verification import (
    exact_arithmetic,evaluate_checks,parse_judgment,verify_turn,
)
from skeleton.app.jeeves_turn_feedback import TurnFeedback
from skeleton.app.offline_web import HTML,JAVASCRIPT

MODEL="a"*64
TOKENIZER="b"*64
PEER="c"*64


def spec(*,modalities=None,model=PEER):
    modes=modalities or ["text"]
    return PeerSpec.parse({"schema":"skeleton.jeeves.native-peer.v1",
        "binary":{"path":"/opt/jeeves/llama-server","sha256":"d"*64},
        "model":{"path":"/opt/jeeves/peer.gguf","sha256":model},
        "projector":{"path":"/opt/jeeves/mmproj.gguf","sha256":"e"*64}
                    if set(modes)!={"text"} else None,
        "modalities":modes,"context_tokens":8192,"max_output_tokens":1024,
        "threads":2,"timeout_seconds":120})


class ScriptedPeer:
    def __init__(self,configuration,answer):
        self.spec=configuration
        self.answer=answer;self.calls=[]
    def generate(self,messages,*,max_output_tokens,deadline=None):
        self.calls.append({"messages":messages,"budget":max_output_tokens})
        receipt={"peer_identity":self.spec.identity,"model_sha256":self.spec.model.sha256,
                 "output_sha256":digest(self.answer),"finish_reason":"stop"}
        receipt["sha256"]=digest(stable(receipt))
        return {"text":self.answer,"receipt":receipt}


def wav_data():
    target=io.BytesIO()
    with wave.open(target,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b"\x01\x02"*800)
    return target.getvalue()


def media_body(raw,configuration,**changes):
    value={"media_type":"audio/wav","media_base64":base64.b64encode(raw).decode(),
           "source_sha256":hashlib.sha256(raw).hexdigest(),"question":"What is audible?",
           "max_output_tokens":128,"frame_count":1,"expected_peer_identity":configuration.identity,
           "approved":True}
    return value|changes


class NativePeerTests(unittest.TestCase):
    def test_configuration_closed_schema_and_distinct_modes(self):
        configuration=spec(modalities=["audio","text","image"])
        self.assertEqual(configuration.modalities,("audio","image","text"))
        self.assertEqual(NativePeer(configuration).spec,configuration)
        self.assertNotIn("path",stable(configuration.public()))
        for changes in ({"threads":True},{"context_tokens":1},{"modalities":["audio"]},
                        {"projector":None},{"max_output_tokens":8192},{"extra_args":["--host","0.0.0.0"]}):
            with self.subTest(changes=changes),self.assertRaises(PeerRejected):
                PeerSpec.parse(configuration.as_dict()|changes)

    def test_path_and_asset_identity(self):
        configuration=spec()
        moved=configuration.as_dict()
        moved["model"]=moved["model"]|{"path":"/srv/jeeves/another.gguf"}
        self.assertEqual(PeerSpec.parse(moved).identity,configuration.identity)
        self.assertNotEqual(spec(model="f"*64).identity,configuration.identity)
        for path in ("relative.gguf","https://example.com/model","/opt/../model.gguf"):
            value=configuration.as_dict()
            value["model"]=value["model"]|{"path":path}
            with self.subTest(path=path),self.assertRaises(PeerRejected):
                PeerSpec.parse(value)

    def test_reject_untrusted_content_and_remote_media(self):
        configuration=spec(modalities=["text","image","audio"])
        for content in (
                [{"type":"image_url","image_url":{"url":"https://example.org/secret"}}],
                [{"type":"image_url","image_url":{"url":"file:///etc/passwd"}}],
                [{"type":"input_audio","input_audio":{"format":"wav","data":"https://example.org/audio"}}],
                [{"type":"tool_call","name":"exec"}]):
            with self.subTest(content=content),self.assertRaises(PeerRejected):
                _validate_messages([{"role":"user","content":content}],configuration)
        _validate_messages([{"role":"user","content":[{"type":"image_url",
            "image_url":{"url":"data:image/jpeg;base64,YWJj"}}]}],configuration)
        with self.assertRaises(PeerRejected):
            _validate_messages([{"role":"tool","content":"execute"}],configuration)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.assertRaises(PeerRejected):
                strict_json(raw)


class MediaTests(unittest.TestCase):
    def test_actual_pcm_decode_and_inline_audio_dispatch(self):
        configuration=spec(modalities=["text","audio"])
        raw=wav_data()
        part,metadata=audio_part(raw)
        self.assertEqual(metadata["sample_frames"],800)
        self.assertEqual(metadata["sample_rate"],16000)
        self.assertEqual(metadata["duration_ms"],50)
        self.assertEqual(part["type"],"input_audio")
        self.assertEqual(hashlib.sha256(base64.b64decode(part["input_audio"]["data"])).hexdigest(),metadata["sha256"])
        backend=ScriptedPeer(configuration,"fixture observation")
        result=analyze(media_body(raw,configuration),backend)
        sent=backend.calls[0]["messages"][0]["content"]
        self.assertEqual(sent[0],part)
        self.assertEqual(result["mode"],"native-pcm-audio")
        self.assertEqual(result["source_sha256"],hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["semantic_accuracy_certified"])
        self.assertFalse(result["raw_media_persisted_by_adapter"])
        self.assertFalse(result["automatic_chat_write"])

    def test_raw_custody_and_explicit_approval(self):
        configuration=spec(modalities=["text","audio"])
        raw=wav_data()
        for changes in ({"approved":False},{"source_sha256":"0"*64},
                        {"media_base64":"a! !"},{"frame_count":2},{"unexpected":1},
                        {"max_output_tokens":True}):
            with self.subTest(changes=changes),self.assertRaises(PeerRejected):
                _raw_media(media_body(raw,configuration,**changes))
        foreign=ScriptedPeer(spec(modalities=["text","audio"],model="f"*64),"wrong")
        with self.assertRaises(PeerRejected):
            analyze(media_body(raw,configuration),foreign)
        self.assertEqual(foreign.calls,[])

    def test_invalid_audio_header_and_decode(self):
        with self.assertRaises(PeerRejected):
            audio_part(b"not a WAV")
        target=io.BytesIO()
        with wave.open(target,"wb") as w:
            w.setnchannels(1);w.setsampwidth(1);w.setframerate(16000);w.writeframes(b"\x01"*100)
        with self.assertRaises(PeerRejected):
            audio_part(target.getvalue())

    def test_image_pixels_when_pillow_available(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("optional local Pillow unavailable")
        from skeleton.app.jeeves_native_multimodal import image_part
        destination=io.BytesIO()
        with Image.new("RGB",(50,30),(10,80,150)) as image:
            image.save(destination,format="PNG")
        part,details=image_part(destination.getvalue(),"image/png")
        self.assertEqual((details["width"],details["height"]),(50,30))
        raw=base64.b64decode(part["image_url"]["url"].split(",",1)[1])
        self.assertTrue(raw.startswith(b"\xff\xd8"))
        self.assertEqual(details["sha256"],hashlib.sha256(raw).hexdigest())
        with self.assertRaises(PeerRejected):
            image_part(destination.getvalue(),"image/jpeg")


class StoreFixture(unittest.TestCase):
    def setUp(self):
        self.store=OfflineChatStore(":memory:")
        self.addCleanup(self.store.close)
        self.sid=self.store.create(MODEL,TOKENIZER)

    def append(self,question,answer,rid):
        before=self.store.load(self.sid,MODEL,TOKENIZER)
        self.store.commit(session=before,request_id=rid,
            request_digest=_digest_request(question,GenerationConfig(max_new_tokens=32)),
            transcript=before.transcript.append("user",question).append("assistant",answer),
            text=answer,output_digest=digest(answer),prompt_tokens=20,generated_tokens=3,
            execution_receipt_digest=digest("local fixture "+rid))

    def saved(self):
        return self.store.load(self.sid,MODEL,TOKENIZER)


class SemanticCompressionTests(StoreFixture):
    @staticmethod
    def estimate(prompt,budget):
        return {"fits":len(prompt.encode())+budget<=32768}

    def policy(self,through=2,**changes):
        return CompressionPolicy.parse({"through_turn":through,"chunk_bytes":512,
            "map_tokens":64,"final_tokens":128,"max_seconds":30}|changes)

    def setup_history(self):
        self.append("Retain this exact identifier: Ø𐍈-719. "+("α"*600),
                    "Unverified first assistant statement. "+("q"*350),"r1")
        self.append("Correction: never replace the original identifier.",
                    "Understood. "+("β"*600),"r2")
        self.append("Recent content deliberately outside selection.","Recent answer.","r3")

    def test_exact_unicode_partition_and_no_silent_omission(self):
        self.setup_history()
        saved=self.saved()
        history=tuple((m.role,m.content) for m in saved.transcript.messages)
        groups,total=partition(history,self.policy())
        self.assertEqual(total,sum(len(t.encode()) for _,t in history[:4]))
        recovered={i:"" for i in range(4)}
        for group in groups:
            self.assertLessEqual(sum(len(s["text"].encode()) for s in group),512)
            for span in group:
                self.assertEqual(span["start"],len(recovered[span["message_index"]]))
                self.assertEqual(digest(span["text"]),span["text_sha256"])
                recovered[span["message_index"]]+=span["text"]
        self.assertEqual([recovered[i] for i in range(4)],[x[1] for x in history[:4]])

    def test_actual_callback_map_reduce_sequence_without_transcript_write(self):
        self.setup_history()
        original=self.saved()
        policy=self.policy()
        planned=make_plan(original,policy,model_digest=MODEL,tokenizer_digest=TOKENIZER,estimate=self.estimate)
        self.assertGreater(len(planned["chunks"]),4)
        self.assertFalse(planned["generation_performed"])
        calls=[]
        async def generate(prompt,budget):
            i=len(calls);calls.append(prompt)
            answer="Synthetic abstraction fixture "+str(i)
            return {"text":answer,"model_digest":MODEL,"request_sha256":digest(prompt),
                "execution_receipt_digest":digest("fixture pass "+str(i)),
                "input_tokens":12,"output_tokens":4}
        result=asyncio.run(compress(original,policy,planned["plan_sha256"],model_digest=MODEL,
            tokenizer_digest=TOKENIZER,estimate=self.estimate,generate=generate))
        self.assertEqual(len(calls),planned["planned_calls"])
        self.assertEqual(result["nodes"][-1]["kind"],"final")
        self.assertEqual(result["nodes"][-1]["source_chunks"],[r["chunk_id"] for r in planned["chunks"]])
        self.assertFalse(result["semantic_faithfulness_certified"])
        self.assertEqual(review_result(result,self.saved(),estimate=self.estimate),result)
        self.assertEqual(self.saved().transcript.to_json(),original.transcript.to_json())

    def test_stale_plan_and_failed_generation_publish_no_summary(self):
        self.setup_history();prior=self.saved();policy=self.policy()
        plan=make_plan(prior,policy,model_digest=MODEL,tokenizer_digest=TOKENIZER,estimate=self.estimate)
        calls=[]
        async def fail(prompt,budget):
            calls.append(prompt);raise PeerRejected("fixture failure")
        with self.assertRaises(PeerRejected):
            asyncio.run(compress(prior,policy,"0"*64,model_digest=MODEL,
                tokenizer_digest=TOKENIZER,estimate=self.estimate,generate=fail))
        self.assertEqual(calls,[])
        with self.assertRaises(PeerRejected):
            asyncio.run(compress(prior,policy,plan["plan_sha256"],model_digest=MODEL,
                tokenizer_digest=TOKENIZER,estimate=self.estimate,generate=fail))
        self.assertEqual(len(calls),1)
        self.assertEqual(self.saved().revision,3)

    def test_context_and_policy_rejection(self):
        self.setup_history()
        with self.assertRaises(PeerRejected):
            make_plan(self.saved(),self.policy(through=4),model_digest=MODEL,
                      tokenizer_digest=TOKENIZER,estimate=self.estimate)
        with self.assertRaises(PeerRejected):
            make_plan(self.saved(),self.policy(),model_digest=MODEL,
                tokenizer_digest=TOKENIZER,estimate=lambda p,b:{"fits":False})
        with self.assertRaises(PeerRejected):
            self.policy(map_tokens=True)


class IndependentVerificationTests(StoreFixture):
    def test_exact_rational_recomputation_without_executable_eval(self):
        self.assertEqual(exact_arithmetic("(0.1 + 0.2) * 10 / 3"),Fraction(1))
        self.assertEqual(exact_arithmetic("-17/3 + 2"),Fraction(-11,3))
        for expression in ("2**999","1/0","__import__('os')","1//2","[1]","9"*65):
            with self.subTest(expression=expression),self.assertRaises(PeerRejected):
                exact_arithmetic(expression)
        findings=evaluate_checks("Result: 1/3",[
            {"kind":"rational-span","expression":"1/3","start":8,"end":11},
            {"kind":"contains","expected":"Result:"},
            {"kind":"excludes","expected":"missing"},
        ])
        self.assertTrue(findings["all_declared_predicates_passed"])
        self.assertFalse(findings["general_truth_certified"])
        wrong=evaluate_checks("2",[{"kind":"rational-span","expression":"1+2","start":0,"end":1}])
        self.assertEqual(wrong["failed"],1)
        self.assertFalse(evaluate_checks("not JSON",[{"kind":"strict-json"}])["all_declared_predicates_passed"])
        self.assertFalse(evaluate_checks("anything",[])["all_declared_predicates_passed"])

    def test_reviewer_exact_substring_and_consistency(self):
        valid={"verdict":"uncertain","issues":[{"severity":"material",
            "answer_quote":"claim","problem":"Not supported"}],"limitations":"No external source."}
        self.assertEqual(parse_judgment(stable(valid),"A claim."),valid)
        for bad in (valid|{"verdict":"supported"},valid|{"issues":[{"severity":"material",
                            "answer_quote":"missing","problem":"Not supported"}]}):
            with self.assertRaises(PeerRejected):
                parse_judgment(stable(bad),"A claim.")

    def test_distinct_peer_and_deterministic_failure_dominates_favorable_review(self):
        self.append("Give the result of 1 + 1.","3","target")
        feedback=TurnFeedback(self.store,MODEL,TOKENIZER)
        pin={"turn_revision":1,"question_sha256":digest("Give the result of 1 + 1."),
             "raw_answer_sha256":digest("3"),"visible_answer_sha256":digest("3")}
        judgment=stable({"verdict":"supported","issues":[],"limitations":"fixture opinion only"})
        reviewer=ScriptedPeer(spec(),judgment)
        body={"pin":pin,"checks":[{"kind":"rational-span","expression":"1+1","start":0,"end":1}],
              "expected_peer_identity":reviewer.spec.identity,"max_output_tokens":128,"approved":True}
        result=verify_turn(self.store,feedback,self.sid,body,reviewer)
        self.assertEqual(result["disposition"],"declared-predicate-failed")
        self.assertEqual(result["deterministic_checks"]["failed"],1)
        self.assertFalse(result["general_truth_certified"])
        self.assertEqual(self.saved().transcript.messages[-1].content,"3")
        same=ScriptedPeer(spec(model=MODEL),judgment)
        with self.assertRaises(PeerRejected):
            verify_turn(self.store,feedback,self.sid,body|{"expected_peer_identity":same.spec.identity},same)
        self.assertEqual(same.calls,[])

    def test_browser_real_routes_and_controls(self):
        for ident in ("native-media-run","native-media-apply","compression-preview","compression-run",
                      "compression-apply","independent-run","independent-export"):
            self.assertEqual(HTML.count('id="'+ident+'"'),1)
        for route in ("/v1/native-assistance/media","/semantic-compression-preview",
                      "/semantic-compression-run","/independent-review"):
            self.assertIn(route,JAVASCRIPT)


if __name__=="__main__":
    unittest.main()
