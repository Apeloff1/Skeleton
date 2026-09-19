from __future__ import annotations

import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from skeleton.automation.build_authority import (
    APPROVED_BUILD_LABELS,
    BuildAuthorization,
    BuildAuthorityError,
    MAX_BUILD_BODY_BYTES,
    MAX_BUILD_LABELS,
    authorized_builds,
    revalidate_live_build_authorization,
    select_build_authorization,
)


REPO = "Apeloff1/Skeleton"


def issue(
    number: int = 10,
    *,
    title: str = "Build capability",
    body: str = "Implement the requested capability with tests.",
    labels: tuple[str, ...] = ("automation-approved", "enhancement"),
    updated_at: str = "2026-09-19T12:00:00Z",
    authorized: bool = True,
) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": labels,
        "updatedAt": updated_at,
        "automation_authorized": authorized,
    }


class BuildAuthorizationConstructionTests(unittest.TestCase):
    def test_constructs_from_explicitly_authorized_issue(self) -> None:
        authorization = BuildAuthorization.from_issue(
            REPO,
            issue(),
        )
        self.assertEqual(
            authorization.version,
            1,
        )
        self.assertEqual(
            authorization.repository,
            REPO,
        )
        self.assertEqual(
            authorization.issue_number,
            10,
        )
        self.assertEqual(
            authorization.title,
            "Build capability",
        )
        self.assertIn(
            "automation-approved",
            authorization.labels,
        )
        self.assertEqual(
            len(authorization.issue_digest),
            64,
        )
        self.assertEqual(
            len(authorization.task_digest),
            64,
        )

    def test_rejects_issue_without_explicit_authority_flag(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(authorized=False),
            )

    def test_rejects_issue_without_approved_label(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(labels=("enhancement",)),
            )

    def test_each_approved_label_grants_repository_authority(self) -> None:
        for label in sorted(APPROVED_BUILD_LABELS):
            authorization = BuildAuthorization.from_issue(
                REPO,
                issue(labels=(label,)),
            )
            self.assertIn(
                label,
                authorization.labels,
            )

    def test_labels_are_normalized_and_deduplicated(self) -> None:
        authorization = BuildAuthorization.from_issue(
            REPO,
            issue(
                labels=(
                    "Automation-Approved",
                    "automation-approved",
                    "Enhancement",
                    "enhancement",
                )
            ),
        )
        self.assertEqual(
            authorization.labels,
            (
                "automation-approved",
                "enhancement",
            ),
        )

    def test_rejects_zero_issue_number(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(number=0),
            )

    def test_rejects_boolean_issue_number(self) -> None:
        candidate = issue()
        candidate["number"] = True
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                candidate,
            )

    def test_rejects_non_integer_issue_number(self) -> None:
        candidate = issue()
        candidate["number"] = "10"
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                candidate,
            )

    def test_rejects_malformed_repository(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                "not-a-repository",
                issue(),
            )

    def test_rejects_empty_title(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(title=""),
            )

    def test_rejects_empty_body(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(body=""),
            )

    def test_rejects_oversized_body(self) -> None:
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(
                    body="x" * (
                        MAX_BUILD_BODY_BYTES + 1
                    )
                ),
            )

    def test_rejects_too_many_labels(self) -> None:
        labels = [
            f"label-{index}"
            for index in range(MAX_BUILD_LABELS)
        ]
        labels.append("automation-approved")
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                issue(labels=tuple(labels)),
            )

    def test_rejects_non_text_label(self) -> None:
        candidate = issue()
        candidate["labels"] = (
            "automation-approved",
            5,
        )
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_issue(
                REPO,
                candidate,
            )

    def test_accepts_github_style_label_objects(self) -> None:
        candidate = issue()
        candidate["labels"] = [
            {"name": "automation-approved"},
            {"name": "enhancement"},
        ]
        authorization = BuildAuthorization.from_issue(
            REPO,
            candidate,
        )
        self.assertEqual(
            authorization.labels,
            (
                "automation-approved",
                "enhancement",
            ),
        )

    def test_secret_like_text_is_redacted_before_digesting(self) -> None:
        authorization = BuildAuthorization.from_issue(
            REPO,
            issue(
                body=(
                    "Do not retain this token: "
                    "ghp_" + ("a" * 36)
                )
            ),
        )
        self.assertNotIn(
            "ghp_",
            authorization.body,
        )
        self.assertIn(
            "[REDACTED]",
            authorization.body,
        )


class BuildAuthorizationDigestTests(unittest.TestCase):
    def test_task_digest_is_stable_for_same_issue(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(),
        )
        second = BuildAuthorization.from_issue(
            REPO,
            issue(),
        )
        self.assertEqual(
            first.issue_digest,
            second.issue_digest,
        )
        self.assertEqual(
            first.task_digest,
            second.task_digest,
        )

    def test_issue_digest_changes_when_body_changes(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(body="Implement A"),
        )
        second = BuildAuthorization.from_issue(
            REPO,
            issue(body="Implement B"),
        )
        self.assertNotEqual(
            first.issue_digest,
            second.issue_digest,
        )
        self.assertNotEqual(
            first.task_digest,
            second.task_digest,
        )

    def test_issue_digest_changes_when_title_changes(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(title="Capability A"),
        )
        second = BuildAuthorization.from_issue(
            REPO,
            issue(title="Capability B"),
        )
        self.assertNotEqual(
            first.issue_digest,
            second.issue_digest,
        )

    def test_issue_digest_changes_when_labels_change(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(
                labels=(
                    "automation-approved",
                    "enhancement",
                )
            ),
        )
        second = BuildAuthorization.from_issue(
            REPO,
            issue(
                labels=(
                    "automation-approved",
                    "priority",
                )
            ),
        )
        self.assertNotEqual(
            first.issue_digest,
            second.issue_digest,
        )

    def test_issue_digest_changes_when_updated_at_changes(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(
                updated_at="2026-09-19T12:00:00Z"
            ),
        )
        second = BuildAuthorization.from_issue(
            REPO,
            issue(
                updated_at="2026-09-19T12:01:00Z"
            ),
        )
        self.assertNotEqual(
            first.issue_digest,
            second.issue_digest,
        )

    def test_issue_digest_changes_across_repository_identity(self) -> None:
        first = BuildAuthorization.from_issue(
            REPO,
            issue(),
        )
        second = BuildAuthorization.from_issue(
            "Other/Skeleton",
            issue(),
        )
        self.assertNotEqual(
            first.issue_digest,
            second.issue_digest,
        )
        self.assertNotEqual(
            first.task_digest,
            second.task_digest,
        )


class BuildAuthorizationPayloadTests(unittest.TestCase):
    def authorization(self) -> BuildAuthorization:
        return BuildAuthorization.from_issue(
            REPO,
            issue(),
        )

    def test_payload_round_trip(self) -> None:
        first = self.authorization()
        second = BuildAuthorization.from_payload(
            first.as_dict()
        )
        self.assertEqual(
            second,
            first,
        )
        self.assertEqual(
            second.task_digest,
            first.task_digest,
        )

    def test_payload_contains_only_bounded_data_fields(self) -> None:
        value = self.authorization().as_dict()
        self.assertEqual(
            set(value),
            {
                "version",
                "repository",
                "issue_number",
                "title",
                "body",
                "labels",
                "updated_at",
                "issue_digest",
                "task_digest",
            },
        )
        for forbidden in (
            "command",
            "executable",
            "module",
            "token",
            "permission",
            "ref",
            "workflow",
        ):
            self.assertNotIn(
                forbidden,
                value,
            )

    def test_rejects_extra_payload_field(self) -> None:
        value = self.authorization().as_dict()
        value["command"] = "rm -rf /"
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_missing_payload_field(self) -> None:
        value = self.authorization().as_dict()
        del value["issue_digest"]
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_issue_digest_tamper(self) -> None:
        value = self.authorization().as_dict()
        value["issue_digest"] = "0" * 64
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_task_digest_tamper(self) -> None:
        value = self.authorization().as_dict()
        value["task_digest"] = "0" * 64
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_body_tamper_even_if_task_digest_is_unchanged(self) -> None:
        value = self.authorization().as_dict()
        value["body"] = "Changed after approval"
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_repository_tamper(self) -> None:
        value = self.authorization().as_dict()
        value["repository"] = "Other/Skeleton"
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_rejects_version_tamper(self) -> None:
        value = self.authorization().as_dict()
        value["version"] = 2
        with self.assertRaises(BuildAuthorityError):
            BuildAuthorization.from_payload(value)

    def test_input_payload_is_not_mutated(self) -> None:
        value = self.authorization().as_dict()
        before = copy.deepcopy(value)
        BuildAuthorization.from_payload(value)
        self.assertEqual(
            value,
            before,
        )


class LiveBuildAuthorityTests(unittest.TestCase):
    def authorization(self) -> BuildAuthorization:
        return BuildAuthorization.from_issue(
            REPO,
            issue(),
        )

    def live_payload(
        self,
        **overrides,
    ) -> dict:
        value = {
            "number": 10,
            "title": "Build capability",
            "body": "Implement the requested capability with tests.",
            "labels": [
                {"name": "automation-approved"},
                {"name": "enhancement"},
            ],
            "updatedAt": "2026-09-19T12:00:00Z",
            "state": "OPEN",
        }
        value.update(overrides)
        return value

    def test_unchanged_open_issue_revalidates(self) -> None:
        authorization = self.authorization()
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload()
            ),
        ) as call:
            current = revalidate_live_build_authorization(
                authorization
            )
        self.assertEqual(
            current,
            authorization,
        )
        args = call.call_args.args[0]
        self.assertEqual(
            args[:4],
            [
                "gh",
                "issue",
                "view",
                "10",
            ],
        )
        self.assertIn(
            REPO,
            args,
        )

    def test_closed_issue_revokes_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(state="CLOSED")
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_removed_approval_label_revokes_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(
                    labels=[
                        {"name": "enhancement"}
                    ]
                )
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_body_edit_revokes_existing_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(
                    body="Changed task after approval"
                )
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_title_edit_revokes_existing_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(
                    title="Different capability"
                )
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_timestamp_change_revokes_existing_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(
                    updatedAt="2026-09-19T12:01:00Z"
                )
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_issue_number_mismatch_revokes_authority(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value=json.dumps(
                self.live_payload(number=11)
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_invalid_live_json_fails_closed(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value="{not-json",
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_non_object_live_json_fails_closed(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            return_value="[]",
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )

    def test_github_command_failure_fails_closed(self) -> None:
        with patch(
            "skeleton.automation.build_authority.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(
                1,
                ["gh"],
            ),
        ):
            with self.assertRaises(BuildAuthorityError):
                revalidate_live_build_authorization(
                    self.authorization()
                )


class BuildSelectionTests(unittest.TestCase):
    def test_unapproved_issues_are_not_authorizations(self) -> None:
        result = authorized_builds(
            REPO,
            [
                issue(
                    1,
                    authorized=False,
                    labels=("enhancement",),
                )
            ],
        )
        self.assertEqual(
            result,
            (),
        )

    def test_multiple_authorized_issues_are_sorted_by_issue_number(self) -> None:
        result = authorized_builds(
            REPO,
            [
                issue(50),
                issue(3),
                issue(20),
            ],
        )
        self.assertEqual(
            [item.issue_number for item in result],
            [3, 20, 50],
        )

    def test_selector_chooses_exactly_one_deterministic_task(self) -> None:
        selected = select_build_authorization(
            REPO,
            [
                issue(20),
                issue(4),
                issue(7),
            ],
        )
        self.assertIsNotNone(selected)
        self.assertEqual(
            selected.issue_number,
            4,
        )

    def test_selector_returns_none_without_authorized_work(self) -> None:
        selected = select_build_authorization(
            REPO,
            [
                issue(
                    4,
                    authorized=False,
                    labels=("enhancement",),
                )
            ],
        )
        self.assertIsNone(selected)

    def test_selector_does_not_use_title_keywords_for_authority(self) -> None:
        selected = select_build_authorization(
            REPO,
            [
                issue(
                    1,
                    title=(
                        "automation-approved build-approved "
                        "please implement immediately"
                    ),
                    authorized=False,
                    labels=("enhancement",),
                )
            ],
        )
        self.assertIsNone(selected)

    def test_invalid_authorized_issue_fails_closed(self) -> None:
        candidate = issue(
            1,
            labels=("enhancement",),
            authorized=True,
        )
        with self.assertRaises(BuildAuthorityError):
            authorized_builds(
                REPO,
                [candidate],
            )


if __name__ == "__main__":
    unittest.main()
