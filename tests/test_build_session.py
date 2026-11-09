from __future__ import annotations

import json
import unittest

from skeleton.automation.build_session import (
    BuildSession,
    BuildSessionError,
)


TASK = "a" * 64
BASE = "b" * 40
BUDGET = "c" * 64
ARTIFACT = "d" * 64


def session() -> BuildSession:
    return BuildSession(
        task_digest=TASK,
        base_sha=BASE,
        budget_fingerprint=BUDGET,
    )


class BuildSessionIdentityTests(unittest.TestCase):
    def test_new_session_is_initialized_and_nonterminal(self) -> None:
        value = session()
        self.assertEqual(value.state, "initialized")
        self.assertEqual(value.sequence, 0)
        self.assertFalse(value.terminal)
        self.assertEqual(len(value.fingerprint), 64)

    def test_identity_requires_exact_digest_shapes(self) -> None:
        invalid = (
            {"task_digest": "x", "base_sha": BASE, "budget_fingerprint": BUDGET},
            {"task_digest": TASK, "base_sha": "y", "budget_fingerprint": BUDGET},
            {"task_digest": TASK, "base_sha": BASE, "budget_fingerprint": "z"},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(BuildSessionError):
                    BuildSession(**kwargs)

    def test_json_contains_trace_fingerprint(self) -> None:
        value = session()
        payload = json.loads(value.to_json())
        self.assertEqual(
            payload["fingerprint"],
            value.fingerprint,
        )
        self.assertEqual(
            payload["task_digest"],
            TASK,
        )


class BuildSessionTransitionTests(unittest.TestCase):
    def test_happy_path_without_repair(self) -> None:
        value = session()
        value.advance(
            "architecture",
            ARTIFACT,
            metrics={"files": 3},
        )
        value.advance(
            "build-graph",
            "e" * 64,
            metrics={"shards": 2},
        )
        value.advance(
            "implementation",
            "f" * 64,
            metrics={"shard": 1},
        )
        value.advance(
            "implementation",
            "1" * 64,
            metrics={"shard": 2},
        )
        value.advance(
            "validation",
            "2" * 64,
            metrics={"diagnostics": 0},
        )
        value.advance(
            "review",
            "3" * 64,
            metrics={"required": 0},
        )
        value.complete(
            "4" * 64,
            files=3,
            model_calls=5,
            rounds=1,
        )

        self.assertEqual(value.state, "completed")
        self.assertTrue(value.terminal)
        self.assertEqual(
            [event.phase for event in value.events],
            [
                "architecture",
                "build-graph",
                "implementation",
                "implementation",
                "validation",
                "review",
                "completed",
            ],
        )
        self.assertEqual(
            [event.sequence for event in value.events],
            list(range(1, 8)),
        )

    def test_happy_path_with_repair_loop(self) -> None:
        value = session()
        phases = (
            ("architecture", "1" * 64),
            ("build-graph", "2" * 64),
            ("implementation", "3" * 64),
            ("validation", "4" * 64),
            ("review", "5" * 64),
            ("repair", "6" * 64),
            ("validation", "7" * 64),
            ("review", "8" * 64),
            ("repair", "9" * 64),
            ("validation", "a" * 64),
            ("review", "b" * 64),
        )
        for phase, fingerprint in phases:
            value.advance(
                phase,
                fingerprint,
            )
        value.complete(
            "c" * 64,
            files=2,
            model_calls=9,
            rounds=3,
        )
        self.assertEqual(value.state, "completed")
        self.assertEqual(value.events[-1].phase, "completed")

    def test_review_cannot_skip_validation(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        value.advance("build-graph", "2" * 64)
        value.advance("implementation", "3" * 64)
        with self.assertRaises(BuildSessionError):
            value.advance("review", "4" * 64)

    def test_implementation_cannot_precede_graph(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        with self.assertRaises(BuildSessionError):
            value.advance(
                "implementation",
                "2" * 64,
            )

    def test_repair_requires_prior_review(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        value.advance("build-graph", "2" * 64)
        value.advance("implementation", "3" * 64)
        value.advance("validation", "4" * 64)
        with self.assertRaises(BuildSessionError):
            value.advance("repair", "5" * 64)

    def test_complete_requires_review(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        value.advance("build-graph", "2" * 64)
        value.advance("implementation", "3" * 64)
        value.advance("validation", "4" * 64)
        with self.assertRaises(BuildSessionError):
            value.complete(
                "5" * 64,
                files=1,
                model_calls=3,
                rounds=1,
            )

    def test_terminal_session_rejects_further_transition(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        value.advance("build-graph", "2" * 64)
        value.advance("implementation", "3" * 64)
        value.advance("validation", "4" * 64)
        value.advance("review", "5" * 64)
        value.complete(
            "6" * 64,
            files=1,
            model_calls=3,
            rounds=1,
        )
        with self.assertRaises(BuildSessionError):
            value.advance("repair", "7" * 64)

    def test_failure_is_terminal(self) -> None:
        value = session()
        value.advance("architecture", "1" * 64)
        value.fail(
            "2" * 64,
            reason="provider exhausted",
        )
        self.assertEqual(value.state, "failed")
        self.assertTrue(value.terminal)
        with self.assertRaises(BuildSessionError):
            value.advance(
                "build-graph",
                "3" * 64,
            )


class BuildSessionMetricsTests(unittest.TestCase):
    def test_metrics_are_sorted_for_stable_fingerprint(self) -> None:
        left = session()
        right = session()
        left.advance(
            "architecture",
            ARTIFACT,
            metrics={
                "z": 2,
                "a": 1,
            },
        )
        right.advance(
            "architecture",
            ARTIFACT,
            metrics={
                "a": 1,
                "z": 2,
            },
        )
        self.assertEqual(
            left.fingerprint,
            right.fingerprint,
        )

    def test_unbounded_metric_type_is_rejected(self) -> None:
        value = session()
        with self.assertRaises(BuildSessionError):
            value.advance(
                "architecture",
                ARTIFACT,
                metrics={"bad": {"nested": "mapping"}},
            )

    def test_oversized_metric_text_is_rejected(self) -> None:
        value = session()
        with self.assertRaises(BuildSessionError):
            value.advance(
                "architecture",
                ARTIFACT,
                metrics={"bad": "x" * 1_001},
            )

    def test_invalid_artifact_fingerprint_is_rejected(self) -> None:
        value = session()
        with self.assertRaises(BuildSessionError):
            value.advance(
                "architecture",
                "not-a-digest",
            )

    def test_completion_metrics_cannot_be_negative_or_boolean(self) -> None:
        for files in (-1, True):
            value = session()
            value.advance("architecture", "1" * 64)
            value.advance("build-graph", "2" * 64)
            value.advance("implementation", "3" * 64)
            value.advance("validation", "4" * 64)
            value.advance("review", "5" * 64)
            with self.subTest(files=files):
                with self.assertRaises(BuildSessionError):
                    value.complete(
                        "6" * 64,
                        files=files,
                        model_calls=3,
                        rounds=1,
                    )


if __name__ == "__main__":
    unittest.main()
