from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from skeleton.automation.build_authority import (
    BuildAuthorization,
)
from skeleton.automation.build_followup import (
    BuildFollowupError,
    inspect_build_followup,
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
            "body": "Implement the approved feature safely.",
            "labels": ["build-approved"],
            "updatedAt": "2026-09-20T03:00:00Z",
            "automation_authorized": True,
        },
    )


def active_pr() -> dict[str, object]:
    return {
        "number": 42,
        "headRefName": BRANCH,
        "baseRefName": "main",
    }


def pr_payload(
    auth: BuildAuthorization,
    *,
    body: str | None = None,
    head_repo: str = REPO,
    state: str = "open",
) -> str:
    tick = chr(96)
    if body is None:
        body = (
            "Build task digest: "
            + tick
            + auth.task_digest
            + tick
        )
    return json.dumps(
        {
            "number": 42,
            "state": state,
            "body": body,
            "head": {
                "ref": BRANCH,
                "sha": HEAD,
                "repo": {
                    "full_name": head_repo,
                },
            },
            "base": {
                "ref": "main",
            },
        }
    )


def files_payload(
    *,
    filename: str = "skeleton/example.py",
    status: str = "modified",
) -> str:
    return json.dumps(
        [
            {
                "filename": filename,
                "status": status,
            }
        ]
    )


def checks_payload(
    checks: list[dict[str, object]],
) -> str:
    return json.dumps(
        {
            "total_count": len(checks),
            "check_runs": checks,
        }
    )


def check(
    name: str,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    summary: str = "",
) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "details_url": "https://example.invalid/check",
        "output": {
            "title": name,
            "summary": summary,
            "text": "",
        },
    }


class BuildFollowupTests(unittest.TestCase):
    def test_failed_completed_check_is_repairable(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check(
                        "Merge Readiness",
                        conclusion="failure",
                        summary="unit regression",
                    ),
                    check(
                        "Secret scanning",
                        conclusion="success",
                    ),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )

        self.assertEqual(value.state, "failed")
        self.assertTrue(value.repairable)
        self.assertEqual(value.pr_number, 42)
        self.assertEqual(value.branch, BRANCH)
        self.assertEqual(value.head_sha, HEAD)
        self.assertEqual(
            value.changed_paths,
            ("skeleton/example.py",),
        )
        self.assertEqual(
            [item.name for item in value.failed_checks],
            ["Merge Readiness"],
        )
        self.assertEqual(len(value.fingerprint), 64)
        self.assertIn(
            "unit regression",
            value.failure_context(),
        )

    def test_pending_check_defers_repair(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check(
                        "Merge Readiness",
                        conclusion="failure",
                    ),
                    check(
                        "ARM64",
                        status="in_progress",
                        conclusion=None,
                    ),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )
        self.assertEqual(value.state, "pending")
        self.assertFalse(value.repairable)

    def test_all_successful_checks_are_healthy(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check("Merge Readiness"),
                    check("Secret scanning"),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )
        self.assertEqual(value.state, "healthy")
        self.assertFalse(value.repairable)
        self.assertEqual(value.failed_checks, ())

    def test_no_checks_waits_without_repair(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload([]),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )
        self.assertEqual(value.state, "waiting")
        self.assertFalse(value.repairable)

    def test_cancelled_only_does_not_trigger_code_repair(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check(
                        "Merge Readiness",
                        conclusion="cancelled",
                    ),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )
        self.assertEqual(value.state, "failed")
        self.assertFalse(value.repairable)

    def test_timeout_is_repairable(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check(
                        "Integration Smoke",
                        conclusion="timed_out",
                    ),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            value = inspect_build_followup(
                REPO,
                active_pr(),
                auth,
            )
        self.assertTrue(value.repairable)

    def test_task_digest_mismatch_is_rejected(self) -> None:
        auth = authorization()
        tick = chr(96)
        responses = (
            pr_payload(
                auth,
                body=(
                    "Build task digest: "
                    + tick
                    + ("f" * 64)
                    + tick
                ),
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )

    def test_fork_head_is_rejected(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(
                auth,
                head_repo="attacker/fork",
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )

    def test_closed_pr_is_rejected(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(
                auth,
                state="closed",
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )

    def test_blocked_changed_path_is_rejected(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(
                filename="skeleton/automation/secretary.py"
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )

    def test_deleted_file_is_rejected(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(
                status="removed",
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )

    def test_unsupported_terminal_check_conclusion_fails_closed(self) -> None:
        auth = authorization()
        responses = (
            pr_payload(auth),
            files_payload(),
            checks_payload(
                [
                    check(
                        "Unknown",
                        conclusion="mystery",
                    ),
                ]
            ),
        )
        with patch(
            "skeleton.automation.build_followup.subprocess.check_output",
            side_effect=responses,
        ):
            with self.assertRaises(BuildFollowupError):
                inspect_build_followup(
                    REPO,
                    active_pr(),
                    auth,
                )


if __name__ == "__main__":
    unittest.main()
