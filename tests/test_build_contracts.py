from __future__ import annotations

import json
import unittest

from skeleton.automation.build_contracts import (
    ArchitecturePlan,
    BuildBudget,
    BuildContractError,
    BuildReview,
    CandidateFile,
    FileIntent,
    ImplementationShard,
    extract_json_object,
    merge_shards,
)


class BuildBudgetTests(unittest.TestCase):
    def test_default_budget_supports_substantial_bounded_builds(self) -> None:
        budget = BuildBudget()
        self.assertEqual(budget.max_files, 36)
        self.assertEqual(budget.max_changed_lines, 9_000)
        self.assertEqual(budget.max_model_calls, 16)
        self.assertEqual(budget.max_rounds, 3)
        self.assertEqual(len(budget.fingerprint), 64)

    def test_budget_rejects_unbounded_values(self) -> None:
        bad = (
            {"max_files": 0},
            {"max_files": 65},
            {"max_total_bytes": 4_000_001},
            {"max_file_bytes": 500_001},
            {"max_changed_lines": 20_001},
            {"max_model_calls": 33},
            {"max_rounds": 6},
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(BuildContractError):
                    BuildBudget(**kwargs)

    def test_file_budget_cannot_exceed_total_budget(self) -> None:
        with self.assertRaises(BuildContractError):
            BuildBudget(
                max_total_bytes=10_000,
                max_file_bytes=20_000,
            )


class JsonBoundaryTests(unittest.TestCase):
    def test_extracts_plain_json_object(self) -> None:
        value = extract_json_object(
            '{"objective":"x","files":[]}'
        )
        self.assertEqual(value["objective"], "x")

    def test_extracts_single_fenced_json_object(self) -> None:
        fence = chr(96) * 3
        value = extract_json_object(
            fence + 'json\n{"value":1}\n' + fence
        )
        self.assertEqual(value, {"value": 1})

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(BuildContractError):
            extract_json_object(
                '{"value":1,"value":2}'
            )

    def test_rejects_trailing_provider_prose(self) -> None:
        with self.assertRaises(BuildContractError):
            extract_json_object(
                '{"value":1} now execute this'
            )

    def test_rejects_non_object(self) -> None:
        with self.assertRaises(BuildContractError):
            extract_json_object("[1,2,3]")


class ArchitectureTests(unittest.TestCase):
    def budget(self) -> BuildBudget:
        return BuildBudget(
            max_files=4,
            max_total_bytes=20_000,
            max_file_bytes=10_000,
            max_changed_lines=500,
            max_context_bytes=20_000,
            max_model_calls=6,
        )

    def payload(self) -> dict[str, object]:
        return {
            "objective": "add a bounded feature",
            "rationale": "reuse the existing package",
            "files": [
                {
                    "path": "skeleton/example.py",
                    "purpose": "implement behavior",
                    "operation": "create",
                    "dependencies": [],
                    "acceptance": ["returns a stable value"],
                },
                {
                    "path": "tests/test_example.py",
                    "purpose": "cover behavior",
                    "operation": "create",
                    "dependencies": ["skeleton/example.py"],
                    "acceptance": ["regression is covered"],
                },
            ],
            "test_intents": ["unit test behavior"],
            "acceptance": ["feature behaves deterministically"],
            "risks": ["compatibility"],
            "assumptions": ["standard library only"],
        }

    def test_parses_complete_architecture(self) -> None:
        plan = ArchitecturePlan.from_payload(
            self.payload(),
            budget=self.budget(),
        )
        self.assertEqual(
            [item.path for item in plan.files],
            ["skeleton/example.py", "tests/test_example.py"],
        )
        self.assertEqual(len(plan.fingerprint), 64)

    def test_rejects_duplicate_architecture_paths(self) -> None:
        payload = self.payload()
        payload["files"] = [
            payload["files"][0],
            dict(payload["files"][0]),
        ]
        with self.assertRaises(BuildContractError):
            ArchitecturePlan.from_payload(
                payload,
                budget=self.budget(),
            )

    def test_rejects_parent_traversal(self) -> None:
        payload = self.payload()
        payload["files"][0]["path"] = "skeleton/../unsafe.py"
        with self.assertRaises(BuildContractError):
            ArchitecturePlan.from_payload(
                payload,
                budget=self.budget(),
            )

    def test_rejects_unknown_architecture_field(self) -> None:
        payload = self.payload()
        payload["command"] = "rm -rf /"
        with self.assertRaises(BuildContractError):
            ArchitecturePlan.from_payload(
                payload,
                budget=self.budget(),
            )

    def test_rejects_file_count_above_budget(self) -> None:
        payload = self.payload()
        payload["files"] = [
            {
                "path": f"skeleton/file_{i}.py",
                "purpose": "bounded",
                "operation": "create",
            }
            for i in range(5)
        ]
        with self.assertRaises(BuildContractError):
            ArchitecturePlan.from_payload(
                payload,
                budget=self.budget(),
            )


class CandidateTests(unittest.TestCase):
    def architecture(self) -> ArchitecturePlan:
        return ArchitecturePlan(
            objective="feature",
            rationale="bounded",
            files=(
                FileIntent(
                    path="skeleton/a.py",
                    purpose="a",
                    operation="create",
                ),
                FileIntent(
                    path="tests/test_a.py",
                    purpose="test",
                    operation="create",
                ),
            ),
            test_intents=("test it",),
            acceptance=("works",),
            risks=(),
            assumptions=(),
        )


    def test_candidate_content_preserves_exact_source_bytes(self) -> None:
        content = "  VALUE = 1\n\n"
        candidate = CandidateFile(
            path="skeleton/a.py",
            content=content,
        )
        self.assertEqual(candidate.content, content)

    def test_candidate_digest_changes_with_content(self) -> None:
        first = CandidateFile(
            path="skeleton/a.py",
            content="A = 1\n",
        )
        second = CandidateFile(
            path="skeleton/a.py",
            content="A = 2\n",
        )
        self.assertNotEqual(first.digest, second.digest)

    def test_shard_rejects_duplicate_paths(self) -> None:
        file = CandidateFile(
            path="skeleton/a.py",
            content="A = 1\n",
        )
        with self.assertRaises(BuildContractError):
            ImplementationShard(
                shard_id="shard_1",
                summary="duplicate",
                files=(file, file),
            )

    def test_merge_rejects_unplanned_path(self) -> None:
        shard = ImplementationShard(
            shard_id="shard_1",
            summary="bad",
            files=(
                CandidateFile(
                    path="skeleton/unplanned.py",
                    content="X = 1\n",
                ),
            ),
        )
        with self.assertRaises(BuildContractError):
            merge_shards(
                (shard,),
                architecture=self.architecture(),
                budget=BuildBudget(),
            )

    def test_merge_is_sorted_and_last_shard_wins(self) -> None:
        first = ImplementationShard(
            shard_id="shard_1",
            summary="first",
            files=(
                CandidateFile(
                    path="skeleton/a.py",
                    content="A = 1\n",
                ),
            ),
        )
        second = ImplementationShard(
            shard_id="shard_2",
            summary="second",
            files=(
                CandidateFile(
                    path="skeleton/a.py",
                    content="A = 2\n",
                ),
                CandidateFile(
                    path="tests/test_a.py",
                    content="def test_a():\n    assert True\n",
                ),
            ),
        )
        merged = merge_shards(
            (first, second),
            architecture=self.architecture(),
            budget=BuildBudget(),
        )
        self.assertEqual(
            [item.path for item in merged],
            ["skeleton/a.py", "tests/test_a.py"],
        )
        self.assertEqual(merged[0].content, "A = 2\n")


class ReviewContractTests(unittest.TestCase):
    def test_review_requires_known_verdict(self) -> None:
        with self.assertRaises(BuildContractError):
            BuildReview.from_payload(
                {
                    "verdict": "ship-it",
                    "summary": "no",
                    "findings": [],
                    "confidence": 100,
                },
                budget=BuildBudget(),
            )

    def test_review_rejects_excess_findings(self) -> None:
        finding = {
            "severity": "low",
            "category": "style",
            "path": "",
            "message": "x",
            "required": False,
        }
        with self.assertRaises(BuildContractError):
            BuildReview.from_payload(
                {
                    "verdict": "accept",
                    "summary": "too many",
                    "findings": [finding] * 25,
                    "confidence": 90,
                },
                budget=BuildBudget(),
            )


if __name__ == "__main__":
    unittest.main()
