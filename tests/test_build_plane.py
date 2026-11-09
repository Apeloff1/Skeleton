from __future__ import annotations

import json
import unittest

from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.build_contracts import BuildBudget
from skeleton.automation.build_index import IndexEntry, RepositoryIndex
from skeleton.automation.build_plane import (
    BuildPlaneError,
    run_feature_build,
)


HEAD = "a" * 40
REPO = "Apeloff1/Skeleton"


def authorization() -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        {
            "number": 901,
            "title": "Add deterministic generated feature",
            "body": (
                "Implement a deterministic helper and regression coverage "
                "without changing automation authority."
            ),
            "labels": ["build-approved"],
            "updatedAt": "2026-09-20T03:00:00Z",
            "automation_authorized": True,
        },
    )


def empty_index() -> RepositoryIndex:
    return RepositoryIndex(
        head_sha=HEAD,
        entries=(),
        directory_counts=(),
    )


def architecture_payload(
    *,
    path: str = "skeleton/generated_feature.py",
    operation: str = "create",
) -> dict[str, object]:
    return {
        "objective": "Implement the approved deterministic helper.",
        "rationale": "Keep behavior isolated and dependency-free.",
        "files": [
            {
                "path": path,
                "purpose": "Implement approved behavior.",
                "operation": operation,
                "dependencies": [],
                "acceptance": ["Returns the deterministic value."],
            }
        ],
        "test_intents": ["Exercise the helper deterministically."],
        "acceptance": ["Approved helper is present and valid."],
        "risks": ["API compatibility"],
        "assumptions": ["No external dependency is required."],
    }


def implementation_payload(
    content: str = "def generated_value() -> int:\n    return 7\n",
) -> dict[str, object]:
    return {
        "summary": "Implemented the deterministic helper.",
        "files": [
            {
                "path": "skeleton/generated_feature.py",
                "content": content,
                "intent": "approved helper behavior",
            }
        ],
        "tests": ["helper returns seven"],
    }


def accept_review() -> dict[str, object]:
    return {
        "verdict": "accept",
        "summary": "Candidate is coherent and bounded.",
        "confidence": 91,
        "findings": [],
    }


class FakeClient:
    def __init__(self, *payloads: dict[str, object]):
        self.responses = [
            json.dumps(payload, sort_keys=True)
            for payload in payloads
        ]
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def chat(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int,
    ) -> str:
        self.systems.append(system)
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)


class FeatureBuildPlaneTests(unittest.TestCase):
    def test_builds_reviewed_candidate_with_legacy_worker_shape(self) -> None:
        client = FakeClient(
            architecture_payload(),
            implementation_payload(),
            accept_review(),
        )
        result = run_feature_build(
            plan="Implement the explicitly approved issue.",
            build_authorization=authorization(),
            client=client,
            index=empty_index(),
        )

        self.assertEqual(set(result), {"summary", "files", "tests"})
        self.assertEqual(
            result["files"],
            [
                {
                    "path": "skeleton/generated_feature.py",
                    "content": (
                        "def generated_value() -> int:\n"
                        "    return 7\n"
                    ),
                }
            ],
        )
        self.assertIn("Build-plane evidence:", result["summary"])
        self.assertIn("version: 2", result["summary"])
        self.assertEqual(len(client.prompts), 3)
        self.assertTrue(
            any("AUTHORIZED ISSUE" in prompt for prompt in client.prompts)
        )

    def test_repairs_static_blocker_before_acceptance(self) -> None:
        client = FakeClient(
            architecture_payload(),
            implementation_payload("def broken(:\n"),
            implementation_payload(
                "def generated_value() -> int:\n    return 7\n"
            ),
            accept_review(),
        )
        result = run_feature_build(
            plan="Build then repair if validation requires it.",
            build_authorization=authorization(),
            client=client,
            index=empty_index(),
        )

        self.assertEqual(len(client.prompts), 4)
        self.assertIn(
            "def generated_value()",
            result["files"][0]["content"],
        )
        self.assertIn("review rounds: 2/3", result["summary"])
        repair_prompts = [
            prompt
            for prompt in client.prompts
            if "Repair a bounded autonomous build candidate" in prompt
        ]
        self.assertEqual(len(repair_prompts), 1)
        self.assertIn(
            "skeleton/generated_feature.py",
            repair_prompts[0],
        )

    def test_rejects_control_plane_path_before_implementation(self) -> None:
        client = FakeClient(
            architecture_payload(
                path=".github/workflows/unsafe.yml"
            )
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Do not allow authority mutation.",
                build_authorization=authorization(),
                client=client,
                index=empty_index(),
            )
        self.assertEqual(len(client.prompts), 1)

    def test_rejects_security_authority_path_inside_buildable_root(self) -> None:
        client = FakeClient(
            architecture_payload(
                path="core/activation_security.py"
            )
        )
        index = RepositoryIndex(
            head_sha=HEAD,
            entries=(
                IndexEntry(
                    path="core/activation_security.py",
                    bytes=10,
                    lines=1,
                    digest="b" * 40,
                ),
            ),
            directory_counts=(("core", 1),),
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Preserve security authority.",
                build_authorization=authorization(),
                client=client,
                index=index,
            )

    def test_rejects_replace_for_missing_file(self) -> None:
        client = FakeClient(
            architecture_payload(operation="replace")
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Replace only existing files.",
                build_authorization=authorization(),
                client=client,
                index=empty_index(),
            )

    def test_rejects_create_for_existing_file(self) -> None:
        client = FakeClient(
            architecture_payload(
                path="skeleton/existing.py",
                operation="create",
            )
        )
        index = RepositoryIndex(
            head_sha=HEAD,
            entries=(
                IndexEntry(
                    path="skeleton/existing.py",
                    bytes=10,
                    lines=1,
                    digest="c" * 40,
                ),
            ),
            directory_counts=(("skeleton", 1),),
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Respect immutable repository shape.",
                build_authorization=authorization(),
                client=client,
                index=index,
            )

    def test_model_call_budget_fails_closed(self) -> None:
        client = FakeClient(
            architecture_payload(),
            implementation_payload(),
            accept_review(),
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Bound provider calls.",
                build_authorization=authorization(),
                client=client,
                index=empty_index(),
                budget=BuildBudget(
                    max_model_calls=2,
                ),
            )
        self.assertEqual(len(client.prompts), 1)

    def test_repair_round_limit_does_not_publish_unresolved_candidate(self) -> None:
        repair_required = {
            "verdict": "repair",
            "summary": "still incomplete",
            "confidence": 90,
            "findings": [
                {
                    "severity": "high",
                    "category": "integration",
                    "path": "skeleton/generated_feature.py",
                    "message": "still missing required integration",
                    "required": True,
                }
            ],
        }
        client = FakeClient(
            architecture_payload(),
            implementation_payload(),
            repair_required,
            implementation_payload(
                "def generated_value() -> int:\n    return 8\n"
            ),
            repair_required,
        )
        with self.assertRaises(BuildPlaneError):
            run_feature_build(
                plan="Fail closed when review remains unresolved.",
                build_authorization=authorization(),
                client=client,
                index=empty_index(),
                budget=BuildBudget(
                    max_rounds=2,
                ),
            )

    def test_build_task_digest_is_present_in_architecture_prompt(self) -> None:
        auth = authorization()
        client = FakeClient(
            architecture_payload(),
            implementation_payload(),
            accept_review(),
        )
        run_feature_build(
            plan="Use exact task custody.",
            build_authorization=auth,
            client=client,
            index=empty_index(),
        )
        self.assertIn(auth.task_digest, client.prompts[0])


if __name__ == "__main__":
    unittest.main()
