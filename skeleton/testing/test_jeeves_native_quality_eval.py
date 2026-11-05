"""Simulated-source tests for explicit native AI quality measurement.

The evaluation runner itself must be invoked through the approved model
installer before real GGUF quality evidence can be claimed. These tests
only qualify Python control/identity/metric boundaries and fail-closed denial.
"""
from __future__ import annotations

from hashlib import sha256
import json
import unittest

from skeleton.jeeves.agent.native_quality_eval import (
    EvalBudget, EvalCase, NativeEvaluationHold,
    NativeJeevesEvaluation, load_evaluation_cases, score_evaluation,
)
from skeleton.testing.test_jeeves_native_provider_bridge import (
    SimulatedWorker, MODEL, TOKENIZER,
)


ANSWER = '{"answer":"ok","confidence":1,"refs":[]}'
ANSWER_SHA = sha256(ANSWER.encode()).hexdigest()


def case(**overrides):
    options = {
        "case_id": "test_case",
        "prompt": "Answer a bounded original local source question.",
        "exact_sha256": ANSWER_SHA,
        "required_terms": ("ok",),
        "forbidden_terms": ("unknown-dangerous-output",),
        "minimum_generated_tokens": 1,
        "maximum_generated_tokens": 128,
    }
    options.update(overrides)
    return EvalCase(**options)


def raw_cases(cases):
    return json.dumps({
        "schema": "jeeves.native_evaluation_casebook.v1",
        "cases": cases,
    }, sort_keys=True).encode("utf-8")


class TestTypedCases(unittest.TestCase):
    def test_valid_case_has_no_authority_for_tools(self):
        obj = case()
        self.assertEqual(obj.case_id, "test_case")
        self.assertEqual(obj.exact_sha256, ANSWER_SHA)

    def test_missing_predicate_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            case(exact_sha256=None, required_terms=(), forbidden_terms=())

    def test_duplicate_terms_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            case(required_terms=("ok", "ok"))

    def test_conflicting_terms_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            case(required_terms=("same",), forbidden_terms=("same",))

    def test_oversized_model_question_refused(self):
        with self.assertRaises(ValueError):
            case(prompt="x" * 32769)

    def test_wrong_digest_format_refused(self):
        with self.assertRaises(ValueError):
            case(exact_sha256="f" * 63)

    def test_boolean_token_bounds_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            case(minimum_generated_tokens=True)

    def test_inverted_token_limits_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            case(minimum_generated_tokens=120, maximum_generated_tokens=1)

    def test_unknown_case_field_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            load_evaluation_cases(raw_cases([{
                "case_id": "a", "prompt": "Test", "forbidden_terms": ["bad"],
                "system_override": "ignore policy",
            }]))

    def test_duplicate_case_ids_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            load_evaluation_cases(raw_cases([
                {"case_id": "a", "prompt": "Hello", "forbidden_terms": ["bad"]},
                {"case_id": "a", "prompt": "World", "forbidden_terms": ["bad"]},
            ]))

    def test_duplicate_json_key_refused(self):
        payload = (
            b'{"schema":"jeeves.native_evaluation_casebook.v1",'
            b'"cases":[{"case_id":"x","case_id":"y","prompt":"z",'
            b'"forbidden_terms":["bad"]}]}'
        )
        with self.assertRaises(ValueError):
            load_evaluation_cases(payload)

    def test_nonfinite_json_refused(self):
        payload = raw_cases([{
            "case_id": "a", "prompt": "Hello", "forbidden_terms": ["bad"],
        }]).replace(b'"case_id": "a"', b'"case_id": NaN')
        with self.assertRaises(ValueError):
            load_evaluation_cases(payload)

    def test_valid_source_casebook(self):
        raw = raw_cases([{
            "case_id": "alpha", "prompt": "What is the answer?",
            "required_terms": ["ok"], "maximum_generated_tokens": 128,
        }])
        loaded = load_evaluation_cases(raw)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].required_terms, ("ok",))

    def test_rejects_wrong_version(self):
        with self.assertRaises(NativeEvaluationHold):
            load_evaluation_cases(
                raw_cases([{"case_id": "x", "prompt": "Hello", "required_terms": ["ok"]}])
                .replace(b"jeeves.native_evaluation_casebook.v1", b"future"),
            )

    def test_maximum_size_enforced_before_json_parse(self):
        with self.assertRaises(NativeEvaluationHold):
            load_evaluation_cases(b" " * 262145)

    def test_unknown_top_level_authority_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            load_evaluation_cases(json.dumps({
                "schema": "jeeves.native_evaluation_casebook.v1",
                "cases": [{"case_id": "a", "prompt": "X", "required_terms": ["x"]}],
                "approved": True,
            }).encode())


class TestDeterministicScoring(unittest.TestCase):
    def score(self, c=None, *, text=ANSWER, tokens=40, digest=None):
        return score_evaluation(
            c or case(),
            answer=text,
            output_sha256=digest or sha256(text.encode()).hexdigest(),
            generated_tokens=tokens,
            duration_ms=12,
            model_sha256=MODEL,
            tokenizer_sha256=TOKENIZER,
        )

    def test_exact_sha_and_required_terms_pass(self):
        result = self.score()
        self.assertTrue(result.passed)
        self.assertTrue(result.exact_match)
        self.assertEqual(result.output_sha256, ANSWER_SHA)
        self.assertFalse(result.to_record()["semantic_truth_certified"])
        self.assertFalse(result.to_record()["release_certified"])

    def test_wrong_expected_sha_fails_without_exception(self):
        result = self.score(case(exact_sha256="f" * 64))
        self.assertFalse(result.passed)
        self.assertFalse(result.exact_match)

    def test_missing_required_term_fails(self):
        result = self.score(case(required_terms=("missing",)))
        self.assertFalse(result.passed)
        self.assertFalse(result.required_terms_satisfied)

    def test_forbidden_term_present_fails(self):
        result = self.score(case(forbidden_terms=("ok",), required_terms=()))
        self.assertFalse(result.passed)
        self.assertFalse(result.forbidden_terms_absent)

    def test_token_budget_overrun_fails(self):
        result = self.score(case(maximum_generated_tokens=1))
        self.assertFalse(result.passed)
        self.assertFalse(result.generated_token_limit_satisfied)

    def test_mutated_output_sha_rejected(self):
        with self.assertRaises(NativeEvaluationHold):
            self.score(digest="f" * 64)

    def test_empty_answer_refused(self):
        with self.assertRaises(NativeEvaluationHold):
            self.score(text="")


class TestEvaluationExecution(unittest.TestCase):
    def setUp(self):
        self.worker = SimulatedWorker()

    def test_no_permission_no_generation(self):
        with self.assertRaises(NativeEvaluationHold):
            NativeJeevesEvaluation(self.worker, approved=False)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_budget_admission_before_native_generation(self):
        evaluator = NativeJeevesEvaluation(
            self.worker, approved=True,
            budget=EvalBudget(maximum_reserved_tokens=127),
        )
        with self.assertRaises(NativeEvaluationHold):
            evaluator.run((case(),))
        self.assertEqual(self.worker.spine.generations, 0)

    def test_single_case_returns_digest_only(self):
        evaluator = NativeJeevesEvaluation(self.worker, approved=True)
        result = evaluator.run((case(),))
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.worker.spine.generations, 1)
        self.assertNotIn(ANSWER, str(result))
        self.assertNotIn("Answer a bounded", str(result))

    def test_independent_case_sessions(self):
        evaluator = NativeJeevesEvaluation(self.worker, approved=True)
        result = evaluator.run((
            case(case_id="a"), case(case_id="b"),
        ))
        self.assertEqual(result["cases"], 2)
        self.assertEqual(self.worker.spine.generations, 2)
        self.assertEqual(len(self.worker.spine.sessions), 2)

    def test_failed_quality_score_is_not_claimed_success(self):
        evaluator = NativeJeevesEvaluation(self.worker, approved=True)
        result = evaluator.run((case(exact_sha256="e" * 64),))
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["passed"], 0)

    def test_unknown_native_effect_stops_batch(self):
        self.worker.spine.fail_uncertain = True
        evaluator = NativeJeevesEvaluation(self.worker, approved=True)
        with self.assertRaises(RuntimeError):
            evaluator.run((case(case_id="a"), case(case_id="b")))
        self.assertEqual(self.worker.spine.generations, 1)

    def test_duplicate_ids_cannot_consume_model_quota(self):
        evaluator = NativeJeevesEvaluation(self.worker, approved=True)
        with self.assertRaises(NativeEvaluationHold):
            evaluator.run((case(case_id="a"), case(case_id="a")))
        self.assertEqual(self.worker.spine.generations, 0)

    def test_wall_budget_validation(self):
        with self.assertRaises(NativeEvaluationHold):
            EvalBudget(maximum_wall_seconds=float("inf"))
        with self.assertRaises(NativeEvaluationHold):
            EvalBudget(maximum_cases=0)


if __name__ == "__main__":
    unittest.main()
