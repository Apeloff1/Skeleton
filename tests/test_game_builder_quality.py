"""Adversarial scorer/report tests; no weights, provider, or generated code run."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from skeleton.eval.game_builder_quality import (
    GameQualityError, MAX_RESPONSE_BYTES, TASKS, canonical_bytes, digest,
    score_response, select_tasks, strict_json, summarize, taskset_digest,
    taskset_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "game_quality_operator", ROOT / "scripts/evaluate_jeeves_game_builder_quality.py")
OPERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPERATOR)


def score(task_id: str, value: object, **kwargs):
    return score_response(select_tasks(task_ids=(task_id,))[0], json.dumps(value),
                          elapsed_seconds=kwargs.pop("elapsed_seconds", 1.0), **kwargs)


class GameBuilderTasksetTests(unittest.TestCase):
    def test_fixed_taskset_has_unique_ids_and_seven_capability_categories(self):
        self.assertEqual([task.task_id for task in TASKS], [f"gb{i:02}" for i in range(1, 25)])
        self.assertEqual({task.category for task in TASKS}, {
            "requirements", "constraints", "design", "gdscript", "debugging", "grounding", "iteration"})
        self.assertTrue(all(task.prompt and task.fields and task.checks for task in TASKS))

    def test_taskset_digest_binds_prompt_and_expected_checks(self):
        original = taskset_manifest()
        mutated = deepcopy(original)
        mutated["tasks"][0]["prompt"] += " Change a constraint."
        self.assertNotEqual(digest(mutated), taskset_digest())
        mutated = deepcopy(original)
        mutated["tasks"][2]["checks"][0]["expected"] = 4
        self.assertNotEqual(digest(mutated), taskset_digest())
        self.assertEqual(digest(original), taskset_digest())

    def test_plain_baseline_taskset_stays_frozen_for_schema_candidate(self):
        self.assertEqual(taskset_digest(), "ddb5b43ba5aa5c14fc0598f32264dd94e58d0fa0b6f7035901468b5779c28ff1")

    def test_subset_is_canonical_order_and_never_silently_discards_ids(self):
        self.assertEqual([t.task_id for t in select_tasks(task_ids=("gb24", "gb01"))], ["gb01", "gb24"])
        self.assertEqual(len(select_tasks(limit=6)), 6)
        for kwargs in ({"limit": True}, {"limit": 0}, {"limit": 25},
                       {"task_ids": ()}, {"task_ids": ("gb01", "gb01")},
                       {"task_ids": ("not-a-task",)}, {"limit": 3, "task_ids": ("gb01",)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(GameQualityError):
                select_tasks(**kwargs)


class GameBuilderScorerTests(unittest.TestCase):
    def test_real_aliases_and_order_variation_are_accepted(self):
        row = score("gb01", {"features": ["Offline save", "Double-jumping", "Coin collection"]})
        self.assertTrue(row["all_deterministic_checks_pass"])

    def test_unrequested_extra_feature_fails_requirements(self):
        row = score("gb01", {"features": ["coins", "double jump", "local save", "multiplayer"]})
        self.assertEqual(row["dimensions"]["structure"]["fraction"], 1)
        self.assertEqual(row["dimensions"]["requirements"]["fraction"], 0)

    def test_negating_a_required_feature_does_not_match_keywords(self):
        row = score("gb01", {"features": ["do not collect coins", "double jump", "local save"]})
        self.assertFalse(row["all_deterministic_checks_pass"])

    def test_boolean_is_not_an_integer_and_numeric_string_is_not_integer(self):
        for value in (True, "3", 3.0):
            row = score("gb03", {"hits_to_lose": value, "gems_to_win": 5})
            self.assertEqual(row["dimensions"]["structure"]["fraction"], 0)
            self.assertEqual(row["dimensions"]["requirements"]["passed"], 1)

    def test_unknown_fields_fail_structure_without_hiding_partial_measurements(self):
        row = score("gb05", {"server_required": False, "local_save_required": True,
                              "invented_networking": True})
        self.assertFalse(row["all_deterministic_checks_pass"])
        self.assertEqual(row["dimensions"]["requirements"]["fraction"], 1)

    def test_malformed_duplicate_and_nonfinite_json_fail_closed(self):
        task = TASKS[0]
        for text in ('```json\n{}\n```', '{"features":[],"features":["coins"]}',
                     '{"features":NaN}', '{"features":Infinity}', '[]', '{', ''):
            with self.subTest(text=text):
                row = score_response(task, text, elapsed_seconds=0.2)
                self.assertIsNotNone(row["parse_error"])
                self.assertFalse(row["all_deterministic_checks_pass"])

    def test_large_response_rejected_without_silent_truncation(self):
        row = score_response(TASKS[0], 'x' * (MAX_RESPONSE_BYTES + 1), elapsed_seconds=1)
        self.assertEqual(len(row["response_text"]), MAX_RESPONSE_BYTES + 1)
        self.assertFalse(row["all_deterministic_checks_pass"])
        self.assertIsNotNone(row["parse_error"])

    def test_incomplete_generation_is_never_a_complete_task_pass(self):
        row = score("gb19", {"health": 0, "death": True}, finish_reason="length")
        self.assertEqual(row["dimensions"]["correctness"]["fraction"], 1)
        self.assertTrue(row["possibly_truncated"])
        self.assertFalse(row["all_deterministic_checks_pass"])

    def test_static_code_accepts_whitespace_and_comments_but_not_strings(self):
        row = score("gb13", {"code": "velocity.y  += gravity*delta # integrate seconds"})
        self.assertTrue(row["all_deterministic_checks_pass"])
        for code in ('# velocity.y += gravity * delta', '"velocity.y += gravity * delta"',
                     'velocity.y += gravity * delta * delta',
                     'velocity.y += gravity * delta\nOS.execute("attack", [])'):
            with self.subTest(code=code):
                self.assertFalse(score("gb13", {"code": code})["all_deterministic_checks_pass"])

    def test_wrong_gravity_units_and_godot_version_api_fail(self):
        self.assertFalse(score("gb12", {"expression": "direction * speed * delta",
                                        "pass_velocity_argument": True})["all_deterministic_checks_pass"])
        self.assertFalse(score("gb15", {"floor_method": "is_on_floor", "move_method": "move_and_collide"})[
            "all_deterministic_checks_pass"])

    def test_grounding_requires_real_source_and_explicit_uncertainty(self):
        correct = {"levels": 3, "evidence_ids": ["S1"], "engine_version": "not provided"}
        self.assertTrue(score("gb20", correct)["all_deterministic_checks_pass"])
        for change in ({"engine_version": "Godot 4"}, {"evidence_ids": ["S9"]}, {"levels": 30}):
            self.assertFalse(score("gb20", correct | change)["all_deterministic_checks_pass"])
        self.assertFalse(score("gb21", {"max_enemies": 99, "source_id": "S3"})[
            "all_deterministic_checks_pass"])

    def test_iteration_drift_is_separate_from_requested_change(self):
        row = score("gb23", {"offline": False, "lives": 5, "jump_count": 2})
        self.assertEqual(row["dimensions"]["correctness"]["fraction"], 1)
        self.assertEqual(row["dimensions"]["requirements"]["fraction"], 0)

    def test_latency_requires_finite_nonnegative_measurement(self):
        for elapsed in (True, -1, math.nan, math.inf, 86401):
            with self.subTest(elapsed=elapsed), self.assertRaises(GameQualityError):
                score("gb19", {"health": 0, "death": True}, elapsed_seconds=elapsed)

    def test_summary_recomputes_checks_and_keeps_quality_claims_unmeasured(self):
        good = score("gb19", {"health": 0, "death": True}, elapsed_seconds=2)
        wrong = score("gb23", {"offline": False, "lives": 5, "jump_count": 1}, elapsed_seconds=4)
        wrong["all_deterministic_checks_pass"] = True
        wrong["dimensions"]["correctness"]["passed"] = 999
        result = summarize([good, wrong])
        self.assertEqual(result["all_checks_pass_tasks"], 1)
        self.assertEqual(result["latency_seconds"]["median"], 3)
        self.assertFalse(result["latency_seconds"]["tails_qualified"])
        self.assertIsNone(result["aggregate_superiority_score"])
        self.assertFalse(result["competitive_superiority_established"])
        with self.assertRaises(GameQualityError):
            summarize([good, good])


class GameBuilderArtifactTests(unittest.TestCase):
    def make_result(self, directory: Path, identity: dict[str, object], *, index=0,
                    task_id="gb19", previous=None):
        envelope = {"run_sha256": digest(identity), "task_id": task_id,
                    "previous_sha256": previous or digest(identity),
                    "result": score(task_id, {"health": 0, "death": True})}
        envelope["artifact_sha256"] = digest(envelope)
        OPERATOR.create_json(directory / f"{index:02d}-{task_id}.json", envelope)
        return envelope

    def test_create_only_preserves_original_report(self):
        with TemporaryDirectory() as name:
            path = Path(name) / "run.json"
            OPERATOR.create_json(path, {"original": 1})
            with self.assertRaises(FileExistsError):
                OPERATOR.create_json(path, {"replacement": 2})
            self.assertEqual(OPERATOR.read_json(path), {"original": 1})
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_resume_verifies_source_identity_hash_chain_and_score(self):
        identity = {"source": "abc", "model": "pinned"}
        with TemporaryDirectory() as name:
            directory = Path(name)
            envelope = self.make_result(directory, identity)
            self.assertEqual(len(OPERATOR.load_completed(directory, identity, ("gb19",))), 1)
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, {"source": "changed"}, ("gb19",))
            path = directory / "00-gb19.json"
            changed = deepcopy(envelope)
            changed["result"]["response_text"] = '{"health":42,"death":false}'
            path.write_bytes(canonical_bytes(changed))
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, identity, ("gb19",))

    def test_rehashed_fake_score_is_rejected(self):
        identity = {"source": "abc"}
        with TemporaryDirectory() as name:
            directory = Path(name)
            envelope = self.make_result(directory, identity)
            envelope["result"]["all_deterministic_checks_pass"] = False
            envelope.pop("artifact_sha256")
            envelope["artifact_sha256"] = digest(envelope)
            (directory / "00-gb19.json").write_bytes(canonical_bytes(envelope))
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, identity, ("gb19",))

    def test_resume_gap_and_unknown_result_never_skipped(self):
        identity = {"source": "abc"}
        with TemporaryDirectory() as name:
            directory = Path(name)
            self.make_result(directory, identity, index=1)
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, identity, ("gb18", "gb19"))
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, identity, ("gb19",))

    def test_partial_artifact_is_held_and_never_overwritten(self):
        with TemporaryDirectory() as name:
            directory = Path(name)
            (directory / "00-gb19.json").write_text('{"partial":')
            with self.assertRaises(GameQualityError):
                OPERATOR.load_completed(directory, {}, ("gb19",))
            self.assertEqual((directory / "00-gb19.json").read_text(), '{"partial":')

    def test_result_symlink_is_never_followed(self):
        if not hasattr(os, "symlink"):
            self.skipTest("host lacks symlinks")
        with TemporaryDirectory() as name:
            directory = Path(name)
            target = directory / "target.json"
            OPERATOR.create_json(target, {"original": 1})
            link = directory / "result.json"
            link.symlink_to(target)
            with self.assertRaises(GameQualityError):
                OPERATOR.read_json(link)
            with self.assertRaises(FileExistsError):
                OPERATOR.create_json(link, {"replacement": 2})
            self.assertEqual(OPERATOR.read_json(target), {"original": 1})

    def test_source_snapshot_retains_exact_bytes_and_rejects_drift(self):
        name = "skeleton/eval/game_builder_quality.py"
        payload = (ROOT / name).read_bytes()
        from hashlib import sha256
        source = {"files_sha256": {name: sha256(payload).hexdigest()}}
        with TemporaryDirectory() as directory:
            OPERATOR.snapshot_source(Path(directory), source, resume=False)
            OPERATOR.snapshot_source(Path(directory), source, resume=True)
            target = Path(directory) / "source-snapshot" / name
            self.assertEqual(target.read_bytes(), payload)
            target.write_bytes(payload + b"\n# changed\n")
            with self.assertRaises(GameQualityError):
                OPERATOR.snapshot_source(Path(directory), source, resume=True)


class GameBuilderStructuredCandidateTests(unittest.TestCase):
    def test_schema_uses_field_types_without_reference_answers(self):
        from skeleton.skills.tool_contract import validate_json_schema, validate_json_value, ToolContractError
        for task in TASKS:
            schema = OPERATOR.output_schema(task)
            validate_json_schema(schema)
            self.assertEqual(schema["required"], [name for name, _ in task.fields])
            self.assertFalse(schema["additionalProperties"])
            self.assertNotIn('"enum"', json.dumps(schema))
            self.assertNotIn('"const"', json.dumps(schema))
        schema = OPERATOR.output_schema(select_tasks(task_ids=("gb03",))[0])
        # Grammar must allow a wrong answer, leaving correctness to the scorer.
        validate_json_value(schema, {"hits_to_lose": 999, "gems_to_win": -3})
        for value in ({"hits_to_lose": "3", "gems_to_win": 5},
                      {"hits_to_lose": 3},
                      {"hits_to_lose": 3, "gems_to_win": 5, "extra": True}):
            with self.assertRaises(ToolContractError):
                validate_json_value(schema, value)

    def test_structured_results_use_typed_runtime_value_not_text_extraction(self):
        native = SimpleNamespace(text=None, structured_output={"health": 0, "death": True})
        text, representation = OPERATOR.response_text(native, structured=True)
        self.assertEqual(json.loads(text), {"health": 0, "death": True})
        self.assertIn("runtime-validated", representation)
        for invalid in (SimpleNamespace(text='```json\n{}\n```', structured_output=None),
                        SimpleNamespace(text='{"health":0}', structured_output={"health": 0}),
                        SimpleNamespace(text=None, structured_output=[])):
            with self.assertRaises(GameQualityError):
                OPERATOR.response_text(invalid, structured=True)

    def test_plain_default_preserves_raw_text_and_candidate_requires_explicit_flag(self):
        raw = '```json\n{"health":0}\n```'
        text, representation = OPERATOR.response_text(
            SimpleNamespace(text=raw, structured_output=None), structured=False)
        self.assertEqual(text, raw)
        self.assertEqual(representation, "native-text")
        args = OPERATOR.parser().parse_args(["--manifest", "jeeves.json", "--output-dir", "result"])
        self.assertFalse(args.structured_output)


if __name__ == "__main__":
    unittest.main()
