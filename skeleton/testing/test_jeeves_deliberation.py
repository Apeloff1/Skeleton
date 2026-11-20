"""Deterministic contract fixtures; no real language-model performance claims."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _digest_request
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.app.jeeves_approved_memory import ApprovedMemory
from skeleton.app.jeeves_deliberation import (
    DeliberationRejected, Policy, Selection, bind_request, build_plan,
    digest, execute_plan, make_receipt, resolve_notes, stable, validate_receipt,
)
from skeleton.app.offline_http import OfflineHTTPApplication, OfflineHTTPError

MODEL = "a" * 64
TOKENIZER = "b" * 64
SID = "test-session"
QUESTION = "What is the original dragon archive identifier?"
HISTORY = (
    ("user", "Remember: the dragon archive identifier is ø𐍈-791. Never replace it."),
    ("assistant", "The original identifier is ø𐍈-791."),
    ("user", "The unrelated warehouse has a blue cabinet."),
    ("assistant", "Understood."),
    ("user", "We are now discussing the archive."),
    ("assistant", "Proceed."),
)


def policy(strategy="review", mode="recall", pins=None, **changes):
    raw = {
        "strategy": strategy, "history_mode": mode, "recent_turns": 1,
        "recall_bytes": 2048 if mode == "recall" else 0,
        "work_tokens": 64 if strategy != "direct" else 0,
        "memory_pins": pins or [],
    }
    raw.update(changes)
    return Policy.parse(raw)


def estimate(prompt, history, output):
    count = max(1, (len(prompt.encode()) + sum(len(s.encode()) for _, s in history)) // 4)
    return {"input_tokens": count, "context_tokens": 65536,
            "output_tokens": output, "accounting": "exact-native-tokenizer",
            "model_digest": MODEL, "fits": count + output <= 65536}


def plan_for(pol=None, *, history=HISTORY, question=QUESTION, sid=SID, instructions="",
             notes=None, strict=False, estimator=estimate):
    return build_plan(question=question, policy=pol or policy(), session_id=sid,
                      revision=len(history)//2, model_digest=MODEL,
                      tokenizer_digest=TOKENIZER, instructions=instructions,
                      history=history, notes=notes or [], output_tokens=128,
                      strict=strict, estimate=estimator)


class ScriptedPasses:
    """Synthetic backend contract fixture, not an inference implementation."""
    def __init__(self, outputs=None, fail_at=None, cancel_at=None):
        self.outputs = outputs or ["draft candidate", "critique candidate", "final answer"]
        self.calls = []
        self.fail_at, self.cancel_at = fail_at, cancel_at

    async def __call__(self, prompt, history, output):
        i = len(self.calls)
        self.calls.append((prompt, history, output))
        if i == self.fail_at:
            raise DeliberationRejected("fixture overflow")
        if i == self.cancel_at:
            raise asyncio.CancelledError()
        return {
            "text": self.outputs[i],
            "request_sha256": digest("request:" + str(i) + prompt),
            "rendered_input_sha256": digest(stable([prompt, history])),
            "execution_receipt_digest": digest("fixture receipt " + str(i)),
            "input_tokens": 23 + i, "output_tokens": 4 + i,
            "model_digest": MODEL,
        }


def perform(plan, history=HISTORY, question=QUESTION, rid="req-fixture", backend=None):
    backend = backend or ScriptedPasses()
    out, stages = asyncio.run(execute_plan(question=question, plan=plan,
                                           history=history, generate=backend))
    base = _digest_request(question, GenerationConfig(max_new_tokens=plan["output_tokens"]))
    if plan["strict"]:
        base = digest("skeleton.jeeves.require-full-history.v1:" + base)
    selected = Selection(Policy.parse(plan["policy"]), plan["revision"], plan["plan_sha256"])
    request = bind_request(base, selected)
    receipt = make_receipt(plan=plan, stages=stages, request_id=rid,
                           request_digest=request, base_request_digest=base)
    return out, receipt


def validate(receipt, output, *, history=HISTORY, question=QUESTION, instructions=""):
    return validate_receipt(
        receipt, session_id=receipt["session_id"], request_id=receipt["request_id"],
        revision=len(history)//2+1, model_digest=MODEL, tokenizer_digest=TOKENIZER,
        request_digest=receipt["request_digest"], output_digest=digest(output["text"]),
        execution_digest=output["execution_receipt_digest"], question=question,
        history=history, instructions=instructions, prompt_tokens=output["input_tokens"],
        generated_tokens=output["output_tokens"],
    )


def resign(value):
    value["sha256"] = digest(stable({k: v for k, v in value.items() if k != "sha256"}))
    return value


def memory_pin(row):
    return {key: row[key] for key in ("memory_id", "revision", "sha256")}


class DeliberationPlanningTests(unittest.TestCase):
    def test_policy_closed_schema_and_exact_integer(self):
        for extra in ({"unused": True}, {"recent_turns": True}, {"work_tokens": 0},
                      {"memory_pins": "wrong"}, {"recall_bytes": -1},
                      {"history_mode": "anything"}):
            raw = policy().as_dict() | extra
            with self.subTest(extra=extra), self.assertRaises(DeliberationRejected):
                Policy.parse(raw)

    def test_preserve_mode_rejects_budget_and_strict_recall(self):
        with self.assertRaises(DeliberationRejected):
            policy(mode="preserve", recall_bytes=1)
        with self.assertRaises(DeliberationRejected):
            plan_for(strict=True)

    def test_pinned_policy_bounds_and_duplicates(self):
        pin = {"memory_id": "memory-012345", "revision": 1, "sha256": "c"*64}
        for pins in ([pin, pin], [pin]*5, [pin | {"sha256": "bad"}]):
            with self.subTest(pins=pins), self.assertRaises(DeliberationRejected):
                policy(pins=pins)

    def test_direct_preserves_original_turns(self):
        planned = plan_for(policy("direct", "preserve"), strict=True)
        self.assertEqual(planned["retained_history_messages"], len(HISTORY))
        self.assertEqual(planned["omitted_history_messages"], 0)
        self.assertEqual(planned["spans"], [])
        self.assertEqual(planned["base_prompt_sha256"], digest(QUESTION))
        self.assertEqual(planned["total_output_ceiling"], 128)

    def test_unicode_exact_old_user_excerpt_not_assistant_claim(self):
        planned = plan_for()
        self.assertEqual(planned["omitted_history_messages"], 4)
        self.assertEqual(planned["retained_history_messages"], 2)
        self.assertTrue(planned["spans"])
        for span in planned["spans"]:
            role, text = HISTORY[span["message_index"]]
            self.assertEqual(role, "user")
            self.assertEqual(text[span["start"]:span["end"]], span["text"])
            self.assertEqual(digest(text), span["source_sha256"])
        self.assertTrue(any("ø𐍈-791" in row["text"] for row in planned["spans"]))
        self.assertFalse(planned["older_messages_deleted"])
        self.assertFalse(planned["semantic_compression"])

    def test_tiny_recall_budget_and_no_implicit_history_omission(self):
        limited = plan_for(policy(recall_bytes=0))
        self.assertEqual(limited["spans"], [])
        self.assertEqual(limited["omitted_history_messages"], 4)
        preserved = plan_for(policy("direct", "preserve"))
        self.assertEqual(preserved["omitted_history_messages"], 0)

    def test_conservative_context_overflow_fails_closed(self):
        def tiny(prompt, history, output):
            return estimate(prompt, history, output) | {"context_tokens": 1, "fits": False}
        with self.assertRaises(DeliberationRejected):
            plan_for(estimator=tiny)
        def contradictory(prompt, history, output):
            return estimate(prompt, history, output) | {"fits": False}
        with self.assertRaises(DeliberationRejected):
            plan_for(estimator=contradictory)

    def test_deterministic_read_only_plan_and_changed_original(self):
        first, second = plan_for(), plan_for()
        self.assertEqual(first, second)
        self.assertNotEqual(first["plan_sha256"], plan_for(question="What cabinet?")["plan_sha256"])
        self.assertFalse(first["generation_performed"])
        self.assertFalse(first["later_stage_fit_guaranteed"])
        self.assertTrue(first["read_only"])

    def test_history_revision_mismatch_or_roles(self):
        with self.assertRaises(DeliberationRejected):
            plan_for(history=(("assistant", "bad role"), ("user", "bad order")))
        with self.assertRaises(DeliberationRejected):
            plan_for(history=HISTORY[:-1])

    def test_selected_memory_pin_and_stale_revision(self):
        store = OfflineChatStore(":memory:")
        try:
            mem = ApprovedMemory(store, MODEL, TOKENIZER)
            note = mem.save(kind="fact", label="Archive", text="Archive 791", tags=[],
                            expires_at=None, source=None, approved=True)
            pol = policy(pins=[memory_pin(note)])
            rows = resolve_notes(mem, pol)
            planned = plan_for(pol, notes=rows)
            self.assertEqual(planned["notes"][0]["text"], "Archive 791")
            updated = mem.save(kind="fact", label="Archive", text="Archive 892", tags=[],
                               expires_at=None, source=None, approved=True, pin=memory_pin(note))
            self.assertNotEqual(note["sha256"], updated["sha256"])
            with self.assertRaises((DeliberationRejected, RuntimeContractError, ValueError)):
                resolve_notes(mem, pol)
        finally:
            store.close()


class DeliberationExecutionTests(unittest.TestCase):
    def test_strategy_stage_counts_and_retained_history(self):
        for strategy, count in (("direct", 1), ("refine", 2), ("review", 3)):
            with self.subTest(strategy=strategy):
                planned = plan_for(policy(strategy))
                backend = ScriptedPasses()
                output, receipt = perform(planned, backend=backend)
                self.assertEqual(len(backend.calls), count)
                self.assertEqual(len(receipt["stages"]), count)
                self.assertEqual(receipt["stages"][-1]["stage"], "final")
                self.assertEqual(receipt["final_output_sha256"], digest(output["text"]))
                self.assertEqual(sum(row["output_tokens"] for row in receipt["stages"]),
                                 receipt["total_output_tokens"])
                self.assertEqual(validate(receipt, output), receipt)
                self.assertTrue(all(history == HISTORY[-2:] for _, history, _ in backend.calls))

    def test_refinement_contains_prior_content_but_receipt_retains_only_digests(self):
        planned = plan_for()
        backend = ScriptedPasses(["private draft 𐍈" * 900, "private critique", "answer"])
        output, receipt = perform(planned, backend=backend)
        self.assertIn("private draft", backend.calls[1][0])
        self.assertIn("private critique", backend.calls[2][0])
        self.assertNotIn("private draft", stable(receipt))
        self.assertNotIn("private critique", stable(receipt))
        self.assertFalse(receipt["intermediate_text_retained"])
        self.assertEqual(output["text"], "answer")
        self.assertGreater(receipt["stages"][1]["intermediate_context"][0]["omitted_utf8_bytes"], 0)
        validate(receipt, output)

    def test_stage_failure_does_not_fall_back_to_partial_draft(self):
        backend = ScriptedPasses(fail_at=1)
        with self.assertRaises(DeliberationRejected):
            perform(plan_for(), backend=backend)
        self.assertEqual(len(backend.calls), 2)

    def test_cancellation_does_not_continue_to_final(self):
        backend = ScriptedPasses(cancel_at=1)
        with self.assertRaises(asyncio.CancelledError):
            perform(plan_for(), backend=backend)
        self.assertEqual(len(backend.calls), 2)

    def test_corrected_plan_digest_alone_cannot_bind_changed_history(self):
        planned = plan_for()
        with self.assertRaises(DeliberationRejected):
            perform(planned, history=HISTORY[:-2]+(("user","new"),("assistant","reply")))

    def test_malformed_backend_result_rejected(self):
        for field, value in (("output_tokens", 9000), ("input_tokens", True),
                             ("model_digest", "c"*64), ("text", ""),
                             ("execution_receipt_digest", "invalid")):
            async def backend(prompt, history, output):
                result = await ScriptedPasses()(prompt, history, output)
                result[field] = value
                return result
            with self.subTest(field=field), self.assertRaises(DeliberationRejected):
                perform(plan_for(), backend=backend)

    def test_duplicate_stage_receipts_rejected(self):
        async def backend(prompt, history, output):
            return await ScriptedPasses()(prompt, history, output)
        with self.assertRaises(DeliberationRejected):
            perform(plan_for(), backend=backend)

    def test_receipt_tampering_even_after_resigning_rejected(self):
        output, receipt = perform(plan_for())
        mutations = (
            lambda r: r["stages"].pop(),
            lambda r: r["stages"][-1].update(output_sha256="d"*64),
            lambda r: r["stages"][1]["intermediate_context"][0].update(output_sha256="e"*64),
            lambda r: r.update(total_output_tokens=999),
            lambda r: r.update(independent_verification=True),
            lambda r: r["plan"].update(omitted_history_messages=0),
        )
        for mutate in mutations:
            changed = copy.deepcopy(receipt)
            mutate(changed)
            resign(changed)
            with self.assertRaises(DeliberationRejected):
                validate(changed, output)

    def test_http_request_identity_binds_reviewed_plan(self):
        planned = plan_for()
        selected = Selection(Policy.parse(planned["policy"]), planned["revision"], planned["plan_sha256"])
        raw = {"message": QUESTION,"request_id":"fixture-id","max_output_tokens":128}
        _, plain = OfflineHTTPApplication._turn_identity(raw, 128)
        _, reviewed = OfflineHTTPApplication._turn_identity(raw | {"deliberation":selected.as_dict()},128)
        self.assertNotEqual(plain, reviewed)
        with self.assertRaises(OfflineHTTPError):
            OfflineHTTPApplication._turn_identity(raw | {"grounded":True,
                "deliberation":selected.as_dict()},128)


class DeliberationStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = OfflineChatStore(":memory:")
        self.sid = self.store.create(MODEL, TOKENIZER)

    def tearDown(self):
        self.store.close()

    def append(self, question, answer, rid):
        before = self.store.load(self.sid, MODEL, TOKENIZER)
        request = _digest_request(question, GenerationConfig(max_new_tokens=32))
        self.store.commit(session=before, request_id=rid, request_digest=request,
                          transcript=before.transcript.append("user",question).append("assistant",answer),
                          text=answer,output_digest=digest(answer),prompt_tokens=10,generated_tokens=3)

    def prepared(self):
        for i in range(0,len(HISTORY),2):
            self.append(HISTORY[i][1], HISTORY[i+1][1], "previous-"+str(i))
        saved = self.store.load(self.sid, MODEL, TOKENIZER)
        planned = plan_for(sid=self.sid)
        output, receipt = perform(planned)
        arguments = dict(session=saved,request_id=receipt["request_id"],
            request_digest=receipt["request_digest"],
            transcript=saved.transcript.append("user",QUESTION).append("assistant",output["text"]),
            text=output["text"],output_digest=digest(output["text"]),
            prompt_tokens=output["input_tokens"],generated_tokens=output["output_tokens"],
            execution_receipt_digest=output["execution_receipt_digest"],deliberation_receipt=receipt)
        return arguments, receipt

    def test_durable_atomic_sidecar_and_exact_replay(self):
        arguments, receipt = self.prepared()
        actual = self.store.commit(**arguments)
        self.assertEqual(actual.revision, 4)
        self.assertEqual(self.store.turn_deliberation(self.sid,MODEL,TOKENIZER,
                         request_id=receipt["request_id"]), receipt)
        self.assertEqual(self.store.turn_deliberation(self.sid,MODEL,TOKENIZER)[:-1],[None]*3)
        replay = self.store.commit(**arguments)
        self.assertTrue(replay.replayed)
        saved = self.store.load(self.sid,MODEL,TOKENIZER)
        self.assertEqual(saved.transcript.messages[-2].content, QUESTION)
        self.assertNotIn("draft candidate",saved.transcript.to_json())

    def test_invalid_sidecar_no_transcript_or_turn_publish(self):
        arguments, receipt = self.prepared()
        changed = copy.deepcopy(receipt)
        changed["final_output_sha256"] = "e"*64
        resign(changed)
        with self.assertRaises(RuntimeContractError):
            self.store.commit(**(arguments | {"deliberation_receipt":changed}))
        self.assertEqual(self.store.load(self.sid,MODEL,TOKENIZER).revision,3)
        self.assertEqual(self.store.turn_deliberation(self.sid,MODEL,TOKENIZER),[None]*3)

    def test_missing_required_sidecar_detected_on_load(self):
        arguments, receipt = self.prepared()
        self.store.commit(**arguments)
        with self.store._transaction():
            self.store._db.execute("DELETE FROM offline_turn_deliberation WHERE session_id=?",
                                   (self.sid,))
        with self.assertRaises(RuntimeContractError):
            self.store.load(self.sid,MODEL,TOKENIZER)

    def test_fork_does_not_copy_execution_evidence(self):
        arguments, receipt = self.prepared()
        self.store.commit(**arguments)
        fork = self.store.fork(self.sid,MODEL,TOKENIZER,after_turn=4)
        self.assertEqual(self.store.load(fork,MODEL,TOKENIZER).revision,4)
        self.assertEqual(self.store.turn_deliberation(fork,MODEL,TOKENIZER),[None]*4)


if __name__ == "__main__":
    unittest.main()
