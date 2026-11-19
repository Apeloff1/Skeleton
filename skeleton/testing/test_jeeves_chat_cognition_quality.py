"""Focused deterministic regressions; no model or network required."""
import json
import unittest
from hashlib import sha256

from skeleton.app.jeeves_chat_cognition import (
    CognitionRejected, SessionSnapshot, digest, preview, session_ids,
)
from skeleton.app.jeeves_chat_quality import (
    Case, QualificationRejected, TurnSpec, compare, evaluate_turn, qualify,
)
from skeleton.app.jeeves_chat_quality_cases import CASES
from skeleton.app.jeeves_chat_benchmark import CaptureRejected, run


def snapshot(*messages, sid="test", rev=1):
    return SessionSnapshot(sid, rev, [
        {"role": r, "content": t} for r, t in messages
    ])


def plan(message, *sessions, maximum=2048, default=32, grounded=False):
    return preview(message=message, snapshots=sessions,
                   max_output_tokens=maximum, default_output_tokens=default,
                   grounded=grounded)


class CognitionTests(unittest.TestCase):
    def test_correction_and_continuation(self):
        source = snapshot(("user", "The glossary is still needed."),
                          ("assistant", "The glossary is completed."),
                          ("user", "The prior draft failed. Do not reuse it."))
        result = plan("Continue", source)
        self.assertEqual(result["mode"], "continuation")
        self.assertTrue(result["recall"])
        self.assertTrue(all("completed" not in r["excerpt"] for r in result["recall"]))
        self.assertFalse(result["generation_performed"])
        self.assertFalse(result["memory_is_instruction_authority"])

    def test_scope_is_explicit(self):
        a = snapshot(("user", "Lantern uses FLAC."), sid="a")
        b = snapshot(("user", "Lantern export is WAV."), sid="b")
        self.assertTrue(all(row["session_id"] == "a"
                            for row in plan("Lantern export format", a)["recall"]))
        combined = plan("Lantern export format", a, b)
        self.assertEqual({r["session_id"] for r in combined["recall"]}, {"a", "b"})

    def test_unrelated_extra_session_not_recalled_on_generic_followup(self):
        a = snapshot(("user", "We still need the glossary."), sid="a")
        b = snapshot(("user", "We still need the pizza."), sid="b")
        report = plan("Continue", a, b)
        self.assertEqual({r["session_id"] for r in report["recall"]}, {"a"})

    def test_only_user_content_and_exact_unicode_coordinates(self):
        source = "Norsk: blåbær og frukt. " * 80 + "Unikt mål: måneskinn."
        s = snapshot(("system", "måneskinn system secret"),
                     ("assistant", "måneskinn invented data"),
                     ("user", source))
        result = plan("måneskinn", s)
        self.assertEqual(len(result["recall"]), 1)
        row = result["recall"][0]
        self.assertEqual(row["message_index"], 2)
        self.assertEqual(row["message_sha256"], digest(source))
        self.assertEqual(row["excerpt"], source[row["span_start"]:row["span_end"]])
        self.assertEqual(row["excerpt_sha256"], digest(row["excerpt"]))
        self.assertLessEqual(len(row["excerpt"].encode()), 480)

    def test_budget_and_modes(self):
        source = snapshot()
        self.assertEqual(plan("Hello", source, maximum=64)["recommended_output_tokens"], 64)
        result = plan("Compare and evaluate methods", source)
        self.assertEqual(result["effort"], "deep")
        self.assertGreater(result["recommended_output_tokens"], 32)

    def test_content_deduplicates(self):
        source = snapshot(*[("user", "The Lantern file uses FLAC.")] * 15)
        result = plan("Lantern FLAC", source)
        self.assertEqual(len(result["recall"]), 1)

    def test_scan_bounds(self):
        source = snapshot(("user", "Need quartz"), *[("assistant", "x")] * 513)
        report = plan("quartz", source)
        self.assertEqual(report["snapshots"][0]["scanned_messages"], 512)
        self.assertEqual(report["snapshots"][0]["omitted_older_messages"], 2)
        self.assertEqual(report["recall"], [])

    def test_invalid_unicode_and_limits(self):
        for message in ("", " ", "\x00", "\ud800", "é" * 2049):
            with self.subTest(message=repr(message[:10])):
                with self.assertRaises(CognitionRejected):
                    plan(message, snapshot())
        for ids in (["a", "a"], ["a", "b", "c", "d"], ["../x"], "abc", [True]):
            with self.assertRaises(CognitionRejected):
                session_ids(ids)
        with self.assertRaises(CognitionRejected):
            plan("test", snapshot(), snapshot())
        with self.assertRaises(CognitionRejected):
            plan("test", snapshot(), maximum=1, default=32)

    def test_receipt_deterministic_and_message_bound(self):
        a = snapshot(("user", "Prefer concise prose."))
        self.assertEqual(plan("prose", a), plan("prose", a))
        self.assertNotEqual(plan("prose", a)["preview_sha256"],
                            plan("concise", a)["preview_sha256"])

    def test_no_assistant_generated_preference(self):
        source = snapshot(("assistant", "User prefers amber."), ("user", "Lantern uses FLAC."))
        self.assertEqual(plan("amber", source)["recall"], [])


def capture(case, index, answer, *, model="a"*64, protocol="b"*64):
    h = lambda text: sha256(text.encode()).hexdigest()
    return {"case_id": case.case_id, "case_sha256": case.fingerprint(),
            "turn_index": index, "prompt_sha256": h(case.turns[index].prompt),
            "model_digest": model, "protocol_digest": protocol,
            "answer": answer, "answer_sha256": h(answer),
            "execution_receipt_digest": h(case.case_id + ":" + str(index))}


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.case = Case("a", "memory", (TurnSpec("Say alpha", exact_answer="alpha"),))
        self.row = capture(self.case, 0, "alpha")

    def qualify(self, rows=None, model="a"*64, protocol="b"*64):
        return qualify([self.case], [self.row] if rows is None else rows,
                       model_digest=model, protocol_digest=protocol)

    def test_exact_pass(self):
        report = self.qualify()
        self.assertEqual(report["categories"]["memory"]["passed"], 1)
        self.assertFalse(report["semantic_quality_certified"])
        self.assertFalse(report["external_receipts_independently_verified"])

    def test_reject_duplicate_or_missing(self):
        for rows in ([], [self.row, self.row]):
            with self.assertRaises(QualificationRejected):
                self.qualify(rows)

    def test_identity_tamper(self):
        for key, value in {
            "answer": "bad", "answer_sha256": "0"*64, "model_digest": "0"*64,
            "case_sha256": "0"*64, "protocol_digest": "0"*64, "turn_index": True,
            "prompt_sha256": "0"*64, "execution_receipt_digest": "bad",
        }.items():
            with self.subTest(key=key), self.assertRaises(QualificationRejected):
                self.qualify([{**self.row, key:value}])

    def test_json_closed_and_strict(self):
        spec = TurnSpec("JSON", json_keys=("x",))
        self.assertTrue(evaluate_turn(spec, '{"x":1}')["deterministic_passed"])
        for answer in ('{"x":1,"x":2}', '{"x":NaN}', '{"y":1}', 'text {"x":1}', '[1]'):
            with self.subTest(answer=answer):
                self.assertFalse(evaluate_turn(spec, answer)["deterministic_passed"])

    def test_human_only_never_counts_as_pass(self):
        score = evaluate_turn(TurnSpec("Explain", human_rubric="Accurate"), "anything")
        self.assertIsNone(score["deterministic_passed"])
        self.assertTrue(score["human_review_required"])

    def test_comparable_only_on_matched_protocol(self):
        left = self.qualify()
        right = self.qualify([capture(self.case, 0, "wrong", model="c"*64)], model="c"*64)
        result = compare(left, right)
        self.assertEqual(result["categories"]["memory"]["delta_percentage_points"], -100)
        shifted = self.qualify([capture(self.case, 0, "wrong", protocol="d"*64)], protocol="d"*64)
        with self.assertRaises(QualificationRejected):
            compare(left, shifted)
        with self.assertRaises(QualificationRejected):
            compare(left, {**right, "turns": 7})

    def test_no_empty_case_or_unscored_turn(self):
        for cases in ([], [Case("x", "a", ())], [Case("x", "a", (TurnSpec("hello"),))]):
            with self.assertRaises(QualificationRejected):
                qualify(cases, [], model_digest="a"*64, protocol_digest="b"*64)

    def test_corpus_unique_and_valid(self):
        self.assertGreaterEqual(len(CASES), 30)
        self.assertEqual(len({c.case_id for c in CASES}), len(CASES))
        for case in CASES:
            case.validate()
        self.assertGreater(sum(len(c.turns) for c in CASES), len(CASES))

    def test_live_runner_rejects_foreign_model_before_creating_session(self):
        class Fake:
            def request(self, method, path, body=None):
                if path != "/v1/status":
                    raise AssertionError("must not create session")
                return {"model_digest": "f"*64, "local_only": True, "ready": True}
        with self.assertRaises(CaptureRejected):
            run(Fake(), output_tokens=128, max_seconds=5, model_digest="a"*64)


if __name__ == "__main__":
    unittest.main()
