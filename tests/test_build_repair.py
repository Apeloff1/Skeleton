from __future__ import annotations

import json
import unittest

from skeleton.automation.build_authority import (
    BuildAuthorization,
)
from skeleton.automation.build_followup import (
    BuildFollowup,
    FailedCheck,
)
from skeleton.automation.build_repair import (
    BuildRepairError,
    run_feature_followup_repair,
)


REPO = "Apeloff1/Skeleton"
HEAD = "d" * 40
BRANCH = (
    "bot/specialist-feature-builder-"
    "aaaaaaaaaaaaaaaa"
)


def authorization() -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        {
            "number": 901,
            "title": "Build approved feature",
            "body": "Implement a deterministic helper.",
            "labels": ["build-approved"],
            "updatedAt": "2026-09-20T03:00:00Z",
            "automation_authorized": True,
        },
    )


def failed_check(
    *,
    conclusion: str = "failure",
) -> FailedCheck:
    return FailedCheck(
        name="Merge Readiness",
        conclusion=conclusion,
        details_url="https://example.invalid/check",
        title="Unit",
        summary="expected 2 but got 1",
        text="",
    )


def followup(
    auth: BuildAuthorization,
    *,
    state: str = "failed",
    checks: tuple[FailedCheck, ...] | None = None,
    task_digest: str | None = None,
) -> BuildFollowup:
    if checks is None:
        checks = (failed_check(),)
    return BuildFollowup(
        repository=REPO,
        pr_number=42,
        branch=BRANCH,
        head_sha=HEAD,
        base_branch="main",
        task_digest=(
            task_digest
            if task_digest is not None
            else auth.task_digest
        ),
        changed_paths=("skeleton/example.py",),
        state=state,
        failed_checks=checks,
        total_checks=max(1, len(checks)),
    )


class FakeIndex:
    def __init__(
        self,
        *,
        head_sha: str = HEAD,
        sources: dict[str, str] | None = None,
    ) -> None:
        self.head_sha = head_sha
        self.sources = sources or {
            "skeleton/example.py": "VALUE = 1\n",
        }

    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.sources))

    def read_text(
        self,
        path: str,
        *,
        max_bytes: int | None = None,
    ) -> str:
        if path not in self.sources:
            raise RuntimeError("missing source")
        value = self.sources[path]
        if (
            max_bytes is not None
            and len(value.encode("utf-8")) > max_bytes
        ):
            raise RuntimeError("source too large")
        return value


class FakeClient:
    def __init__(self, *payloads: dict[str, object]):
        self.responses = [
            json.dumps(value, sort_keys=True)
            for value in payloads
        ]
        self.prompts: list[str] = []

    def chat(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int,
    ) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError(
                "unexpected provider call"
            )
        return self.responses.pop(0)


def repair_payload(
    *,
    replacement: str = "VALUE = 2",
) -> dict[str, object]:
    return {
        "decision": "repair",
        "summary": "Repair the failing deterministic value.",
        "files": [],
        "edits": [
            {
                "path": "skeleton/example.py",
                "intent": "fix failing value",
                "edits": [
                    {
                        "kind": "replace",
                        "anchor": "VALUE = 1",
                        "replacement": replacement,
                    }
                ],
            }
        ],
        "tests": [
            "Merge Readiness should pass",
        ],
    }


def accept_review() -> dict[str, object]:
    return {
        "verdict": "accept",
        "summary": "Repair is bounded and coherent.",
        "confidence": 92,
        "findings": [],
    }


def repair_review() -> dict[str, object]:
    return {
        "verdict": "repair",
        "summary": "Still needs correction.",
        "confidence": 95,
        "findings": [
            {
                "severity": "high",
                "category": "integration",
                "path": "skeleton/example.py",
                "message": "value still violates expected behavior",
                "required": True,
            }
        ],
    }


class BuildRepairTests(unittest.TestCase):
    def test_repair_exact_anchor_then_accept(self) -> None:
        auth = authorization()
        client = FakeClient(
            repair_payload(),
            accept_review(),
        )
        result = run_feature_followup_repair(
            plan="Repair failed CI.",
            build_authorization=auth,
            followup=followup(auth),
            client=client,
            index=FakeIndex(),
        )

        self.assertEqual(
            result["files"],
            [
                {
                    "path": "skeleton/example.py",
                    "content": "VALUE = 2\n",
                }
            ],
        )
        self.assertIn(
            "Build followup evidence:",
            result["summary"],
        )
        self.assertEqual(len(client.prompts), 2)
        self.assertIn(
            "expected 2 but got 1",
            client.prompts[0],
        )

    def test_infrastructure_no_change_is_admitted(self) -> None:
        auth = authorization()
        client = FakeClient(
            {
                "decision": "no_change",
                "summary": "Failure is external runner capacity.",
                "files": [],
                "edits": [],
                "tests": [],
            }
        )
        result = run_feature_followup_repair(
            plan="Do not speculate.",
            build_authorization=auth,
            followup=followup(auth),
            client=client,
            index=FakeIndex(),
        )
        self.assertEqual(result["files"], [])
        self.assertIn(
            "no code change",
            result["summary"],
        )
        self.assertEqual(len(client.prompts), 1)

    def test_nonrepairable_followup_never_calls_model(self) -> None:
        auth = authorization()
        client = FakeClient()
        value = followup(
            auth,
            checks=(
                failed_check(
                    conclusion="cancelled"
                ),
            ),
        )
        result = run_feature_followup_repair(
            plan="Do not mutate cancelled runs.",
            build_authorization=auth,
            followup=value,
            client=client,
            index=FakeIndex(),
        )
        self.assertEqual(result["files"], [])
        self.assertEqual(client.prompts, [])

    def test_task_digest_mismatch_fails_closed(self) -> None:
        auth = authorization()
        client = FakeClient()
        with self.assertRaises(BuildRepairError):
            run_feature_followup_repair(
                plan="Mismatch.",
                build_authorization=auth,
                followup=followup(
                    auth,
                    task_digest="f" * 64,
                ),
                client=client,
                index=FakeIndex(),
            )
        self.assertEqual(client.prompts, [])

    def test_head_mismatch_fails_before_provider(self) -> None:
        auth = authorization()
        client = FakeClient()
        with self.assertRaises(BuildRepairError):
            run_feature_followup_repair(
                plan="Stale head.",
                build_authorization=auth,
                followup=followup(auth),
                client=client,
                index=FakeIndex(
                    head_sha="e" * 40,
                ),
            )
        self.assertEqual(client.prompts, [])

    def test_path_expansion_is_rejected(self) -> None:
        auth = authorization()
        client = FakeClient(
            {
                "decision": "repair",
                "summary": "unsafe expansion",
                "files": [
                    {
                        "path": "skeleton/extra.py",
                        "content": "EXTRA = 1\n",
                    }
                ],
                "edits": [],
                "tests": [],
            }
        )
        with self.assertRaises(BuildRepairError):
            run_feature_followup_repair(
                plan="Stay bounded.",
                build_authorization=auth,
                followup=followup(auth),
                client=client,
                index=FakeIndex(),
            )

    def test_deterministic_validation_can_trigger_second_repair(self) -> None:
        auth = authorization()
        client = FakeClient(
            repair_payload(
                replacement="<<<<<<< broken"
            ),
            {
                "summary": "remove conflict marker",
                "files": [
                    {
                        "path": "skeleton/example.py",
                        "content": "VALUE = 2\n",
                        "intent": "repair deterministic blocker",
                    }
                ],
                "tests": ["syntax and conflict scan pass"],
            },
            accept_review(),
        )
        result = run_feature_followup_repair(
            plan="Repair deterministically.",
            build_authorization=auth,
            followup=followup(auth),
            client=client,
            index=FakeIndex(),
        )
        self.assertEqual(
            result["files"][0]["content"],
            "VALUE = 2\n",
        )
        self.assertEqual(len(client.prompts), 3)

    def test_model_review_required_finding_gets_one_repair_round(self) -> None:
        auth = authorization()
        client = FakeClient(
            repair_payload(),
            repair_review(),
            {
                "summary": "repair review finding",
                "files": [
                    {
                        "path": "skeleton/example.py",
                        "content": "VALUE = 3\n",
                        "intent": "review repair",
                    }
                ],
                "tests": ["integration expectation"],
            },
            accept_review(),
        )
        result = run_feature_followup_repair(
            plan="Converge review.",
            build_authorization=auth,
            followup=followup(auth),
            client=client,
            index=FakeIndex(),
        )
        self.assertEqual(
            result["files"][0]["content"],
            "VALUE = 3\n",
        )
        self.assertEqual(len(client.prompts), 4)

    def test_unresolved_second_review_fails_closed(self) -> None:
        auth = authorization()
        client = FakeClient(
            repair_payload(),
            repair_review(),
            {
                "summary": "attempted repair",
                "files": [
                    {
                        "path": "skeleton/example.py",
                        "content": "VALUE = 3\n",
                        "intent": "repair",
                    }
                ],
                "tests": [],
            },
            repair_review(),
        )
        with self.assertRaises(BuildRepairError):
            run_feature_followup_repair(
                plan="Fail if unresolved.",
                build_authorization=auth,
                followup=followup(auth),
                client=client,
                index=FakeIndex(),
            )

    def test_initial_payload_rejects_unknown_fields(self) -> None:
        auth = authorization()
        client = FakeClient(
            {
                "decision": "repair",
                "summary": "bad",
                "files": [],
                "edits": [],
                "tests": [],
                "command": "execute me",
            }
        )
        with self.assertRaises(BuildRepairError):
            run_feature_followup_repair(
                plan="Reject commands.",
                build_authorization=auth,
                followup=followup(auth),
                client=client,
                index=FakeIndex(),
            )


if __name__ == "__main__":
    unittest.main()
