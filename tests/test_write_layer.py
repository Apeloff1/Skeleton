from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.write_layer import (
    WriteBudget,
    WriteLayerError,
    generate_feature_proposal,
    parse_blueprint,
    parse_file_proposal,
)


REPO = "Apeloff1/Skeleton"


def authorization() -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        {
            "number": 77,
            "title": "Build idea",
            "body": "Add a useful capability and regression tests.",
            "labels": ("automation-approved", "enhancement"),
            "updatedAt": "2026-09-20T01:00:00Z",
            "automation_authorized": True,
        },
    )


def blueprint_json(*, path: str = "skeleton/example.py") -> str:
    return json.dumps(
        {
            "summary": "Implement the requested capability.",
            "tasks": [
                {
                    "id": "T1",
                    "objective": "Add the core implementation.",
                    "paths": [path, "tests/test_example.py"],
                    "acceptance": ["core behavior is covered"],
                }
            ],
            "acceptance": ["feature works deterministically"],
            "tests": ["exercise normal and invalid inputs"],
        }
    )


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, int]] = []

    def chat(self, system: str, user: str, max_tokens: int = 2500) -> str:
        self.calls.append((system, user, max_tokens))
        if not self.responses:
            raise AssertionError("unexpected model call")
        return self.responses.pop(0)


class WriteLayerParsingTests(unittest.TestCase):
    def test_blueprint_accepts_safe_declared_paths(self) -> None:
        result = parse_blueprint(blueprint_json(), WriteBudget())
        self.assertEqual(result.tasks[0].task_id, "T1")
        self.assertEqual(
            result.tasks[0].paths,
            ("skeleton/example.py", "tests/test_example.py"),
        )

    def test_blueprint_rejects_automation_authority_path(self) -> None:
        with self.assertRaises(WriteLayerError):
            parse_blueprint(
                blueprint_json(path="skeleton/automation/secretary.py"),
                WriteBudget(),
            )

    def test_blueprint_rejects_workflow_path(self) -> None:
        with self.assertRaises(WriteLayerError):
            parse_blueprint(
                blueprint_json(path=".github/workflows/ci.yml"),
                WriteBudget(),
            )

    def test_blueprint_rejects_duplicate_json_fields(self) -> None:
        raw = (
            '{"summary":"a","summary":"b","tasks":[],"acceptance":[],"tests":[]}'
        )
        with self.assertRaises(WriteLayerError):
            parse_blueprint(raw, WriteBudget())

    def test_proposal_rejects_undeclared_file(self) -> None:
        raw = json.dumps(
            {
                "summary": "attempt",
                "files": [
                    {
                        "path": "skeleton/other.py",
                        "content": "VALUE = 1\n",
                    }
                ],
                "tests": [],
            }
        )
        with self.assertRaises(WriteLayerError):
            parse_file_proposal(
                raw,
                allowed_paths=frozenset({"skeleton/example.py"}),
                budget=WriteBudget(),
            )

    def test_proposal_rejects_invalid_python(self) -> None:
        raw = json.dumps(
            {
                "summary": "invalid",
                "files": [
                    {
                        "path": "skeleton/example.py",
                        "content": "def broken(:\n",
                    }
                ],
                "tests": [],
            }
        )
        with self.assertRaises(WriteLayerError):
            parse_file_proposal(
                raw,
                allowed_paths=frozenset({"skeleton/example.py"}),
                budget=WriteBudget(),
            )

    def test_file_budget_fails_closed(self) -> None:
        budget = WriteBudget(max_files=1)
        with self.assertRaises(WriteLayerError):
            parse_blueprint(blueprint_json(), budget)


class WriteLayerGenerationTests(unittest.TestCase):
    def test_multi_pass_writer_builds_and_repairs_in_memory(self) -> None:
        responses = [
            json.dumps(
                {
                    "summary": "Two-step plan",
                    "tasks": [
                        {
                            "id": "T1",
                            "objective": "Implement core",
                            "paths": ["skeleton/example.py"],
                            "acceptance": ["returns expected value"],
                        },
                        {
                            "id": "T2",
                            "objective": "Add regression coverage",
                            "paths": ["tests/test_example.py"],
                            "acceptance": ["covers expected value"],
                        },
                    ],
                    "acceptance": ["implementation and test agree"],
                    "tests": ["core returns expected value"],
                }
            ),
            json.dumps(
                {
                    "summary": "core",
                    "files": [
                        {
                            "path": "skeleton/example.py",
                            "content": "def value() -> int:\n    return 1\n",
                        }
                    ],
                    "tests": ["core function"],
                }
            ),
            json.dumps(
                {
                    "summary": "tests",
                    "files": [
                        {
                            "path": "tests/test_example.py",
                            "content": (
                                "from skeleton.example import value\n\n"
                                "def test_value() -> None:\n"
                                "    assert value() == 1\n"
                            ),
                        }
                    ],
                    "tests": ["test value"],
                }
            ),
            json.dumps(
                {
                    "summary": "review repair",
                    "files": [
                        {
                            "path": "skeleton/example.py",
                            "content": (
                                '"""Example capability."""\n\n'
                                "def value() -> int:\n"
                                "    return 1\n"
                            ),
                        }
                    ],
                    "tests": ["test value"],
                }
            ),
        ]
        client = FakeClient(responses)
        with (
            patch(
                "skeleton.automation.write_layer.repository_context",
                return_value="repository context",
            ),
            patch(
                "skeleton.automation.write_layer._git_show",
                return_value=None,
            ),
        ):
            result = generate_feature_proposal(
                client,
                authorization(),
                "approved_work_items feature implement",
            )

        self.assertEqual(len(client.calls), 4)
        self.assertEqual(
            [item["path"] for item in result["files"]],
            ["skeleton/example.py", "tests/test_example.py"],
        )
        core = next(
            item["content"]
            for item in result["files"]
            if item["path"] == "skeleton/example.py"
        )
        self.assertIn("Example capability", core)
        self.assertEqual(
            result["tests"],
            [
                "core returns expected value",
                "core function",
                "test value",
            ],
        )

    def test_review_cannot_escape_blueprint_path_set(self) -> None:
        responses = [
            blueprint_json(),
            json.dumps(
                {
                    "summary": "implementation",
                    "files": [
                        {
                            "path": "skeleton/example.py",
                            "content": "VALUE = 1\n",
                        }
                    ],
                    "tests": [],
                }
            ),
            json.dumps(
                {
                    "summary": "escape",
                    "files": [
                        {
                            "path": "skeleton/unplanned.py",
                            "content": "VALUE = 2\n",
                        }
                    ],
                    "tests": [],
                }
            ),
        ]
        client = FakeClient(responses)
        with (
            patch(
                "skeleton.automation.write_layer.repository_context",
                return_value="ctx",
            ),
            patch(
                "skeleton.automation.write_layer._git_show",
                return_value=None,
            ),
        ):
            with self.assertRaises(WriteLayerError):
                generate_feature_proposal(
                    client,
                    authorization(),
                    "feature implement",
                    budget=WriteBudget(max_passes=3),
                )

    def test_no_changes_skips_review_and_returns_empty_files(self) -> None:
        responses = [
            blueprint_json(),
            json.dumps(
                {
                    "summary": "nothing justified",
                    "files": [],
                    "tests": [],
                }
            ),
        ]
        client = FakeClient(responses)
        with (
            patch(
                "skeleton.automation.write_layer.repository_context",
                return_value="ctx",
            ),
            patch(
                "skeleton.automation.write_layer._git_show",
                return_value=None,
            ),
        ):
            result = generate_feature_proposal(
                client,
                authorization(),
                "feature implement",
                budget=WriteBudget(max_passes=3),
            )
        self.assertEqual(result["files"], [])
        self.assertEqual(len(client.calls), 2)

    def test_existing_identical_file_is_filtered_from_final_proposal(self) -> None:
        responses = [
            json.dumps(
                {
                    "summary": "single",
                    "tasks": [
                        {
                            "id": "T1",
                            "objective": "keep value",
                            "paths": ["skeleton/example.py"],
                            "acceptance": ["value remains"],
                        }
                    ],
                    "acceptance": ["value remains"],
                    "tests": [],
                }
            ),
            json.dumps(
                {
                    "summary": "same",
                    "files": [
                        {
                            "path": "skeleton/example.py",
                            "content": "VALUE = 1\n",
                        }
                    ],
                    "tests": [],
                }
            ),
            json.dumps(
                {
                    "summary": "review",
                    "files": [],
                    "tests": [],
                }
            ),
        ]
        client = FakeClient(responses)

        def show(path: str) -> str | None:
            if path == "skeleton/example.py":
                return "VALUE = 1\n"
            return None

        with (
            patch(
                "skeleton.automation.write_layer.repository_context",
                return_value="ctx",
            ),
            patch(
                "skeleton.automation.write_layer._git_show",
                side_effect=show,
            ),
        ):
            result = generate_feature_proposal(
                client,
                authorization(),
                "feature implement",
            )
        self.assertEqual(result["files"], [])


if __name__ == "__main__":
    unittest.main()
