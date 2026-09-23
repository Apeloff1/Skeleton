from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.automation import secretary, specialist_bots, supervisor
from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.execution_failsafe import retry_token
from skeleton.automation.supervisor_runtime import (
    ExecutionIdentity,
    WorkerCustody,
)

FP = "a" * 64
BASE = "b" * 40
OTHER_BASE = "c" * 40
REPO = "Apeloff1/Skeleton"
EXECUTION = ExecutionIdentity(
    repository=REPO,
    base_sha=BASE,
    default_branch="main",
    run_id="12345",
    run_attempt="1",
)


def execution_env(
    *,
    worker: str = "root-cause",
    snapshot: str = FP,
) -> dict[str, str]:
    env = {
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SHA": BASE,
        "GITHUB_RUN_ID": "12345",
        "GITHUB_RUN_ATTEMPT": "1",
        "SUPERVISOR_BASE_SHA": BASE,
        "SUPERVISOR_DEFAULT_BRANCH": "main",
        "SUPERVISOR_RUN_ID": "12345",
        "SUPERVISOR_RUN_ATTEMPT": "1",
        "SUPERVISOR_EXECUTION_FINGERPRINT": EXECUTION.fingerprint,
        "SUPERVISOR_SNAPSHOT_FINGERPRINT": snapshot,
        "SECRETARY_DELEGATION": "1",
        "SECRETARY_WORKER": worker,
        "SECRETARY_ATTEMPT": "1",
    }
    env["SECRETARY_RETRY_TOKEN"] = (
        retry_token(
            worker=worker,
            attempt=1,
            execution_fingerprint=EXECUTION.fingerprint,
            snapshot_fingerprint=snapshot,
        )
        if len(snapshot) == 64
        else "f" * 64
    )
    return env


def tamper_envelope(
    encoded: str,
    mutate,
) -> str:
    value = json.loads(
        base64.b64decode(
            encoded,
            validate=True,
        ).decode("utf-8")
    )
    mutate(value)
    return base64.b64encode(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii")


class SupervisorEnvelopeTests(unittest.TestCase):
    def snapshot(self) -> supervisor.SupervisorSnapshot:
        return supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(
                {
                    "number": 1,
                    "title": "CI failure",
                },
            ),
            pull_requests=(
                {
                    "number": 2,
                    "title": "repair",
                    "mergeStateStatus": "BLOCKED",
                },
            ),
            workflow_runs=(
                {
                    "databaseId": 3,
                    "conclusion": "failure",
                    "name": "quality",
                },
            ),
        )

    def envelope(self, plan: str = "repair failing CI"):
        snap = self.snapshot()
        return (
            snap,
            supervisor.make_envelope(
                snap,
                plan,
                EXECUTION,
            ),
        )

    def decode(
        self,
        encoded: str,
        *,
        repository: str = REPO,
        execution: ExecutionIdentity = EXECUTION,
        now: int = 1_700_000_000,
    ):
        return secretary.decode_delegation(
            encoded,
            repository=repository,
            expected_execution=execution,
            now=now,
        )

    def test_snapshot_fingerprint_is_stable_across_observation_time(
        self,
    ) -> None:
        first = self.snapshot()
        second = supervisor.SupervisorSnapshot(
            first.repository,
            first.observed_at + 30,
            first.issues,
            first.pull_requests,
            first.workflow_runs,
        )
        self.assertEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_snapshot_fingerprint_changes_with_repository_state(
        self,
    ) -> None:
        first = self.snapshot()
        second = supervisor.SupervisorSnapshot(
            first.repository,
            first.observed_at,
            (),
            first.pull_requests,
            first.workflow_runs,
        )
        self.assertNotEqual(
            first.fingerprint,
            second.fingerprint,
        )

    def test_version_three_envelope_round_trip_binds_execution(
        self,
    ) -> None:
        snap, envelope = self.envelope()
        (
            plan,
            fingerprint,
            execution,
            build_authorization,
        ) = self.decode(
            envelope.to_base64()
        )
        self.assertEqual(
            plan,
            "repair failing CI",
        )
        self.assertEqual(
            fingerprint,
            snap.fingerprint,
        )
        self.assertEqual(
            execution,
            EXECUTION,
        )
        self.assertIsNone(
            build_authorization,
        )

    def test_envelope_payload_contains_only_expected_fields(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        self.assertEqual(
            set(envelope.payload()),
            {
                "version",
                "repository",
                "snapshot_fingerprint",
                "observed_at",
                "plan",
                "execution",
                "execution_fingerprint",
                "build_authorization",
            },
        )

    def test_envelope_rejects_cross_repository_replay(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                repository="other/repository",
            )

    def test_envelope_rejects_cross_execution_replay(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        other = ExecutionIdentity(
            repository=REPO,
            base_sha=OTHER_BASE,
            default_branch="main",
            run_id="12345",
            run_attempt="1",
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                execution=other,
            )

    def test_envelope_rejects_run_id_replay(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        other = ExecutionIdentity(
            repository=REPO,
            base_sha=BASE,
            default_branch="main",
            run_id="99999",
            run_attempt="1",
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                execution=other,
            )

    def test_envelope_rejects_attempt_replay(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        other = ExecutionIdentity(
            repository=REPO,
            base_sha=BASE,
            default_branch="main",
            run_id="12345",
            run_attempt="2",
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                execution=other,
            )

    def test_envelope_rejects_stale_plan(
        self,
    ) -> None:
        snap, envelope = self.envelope()
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                now=(
                    snap.observed_at
                    + secretary.MAX_ENVELOPE_AGE_SECONDS
                    + 1
                ),
            )

    def test_envelope_rejects_far_future_observation(
        self,
    ) -> None:
        snap, envelope = self.envelope()
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(
                envelope.to_base64(),
                now=snap.observed_at - 301,
            )

    def test_envelope_rejects_malformed_base64(
        self,
    ) -> None:
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode("%%%")

    def test_envelope_rejects_unsupported_version(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        encoded = tamper_envelope(
            envelope.to_base64(),
            lambda value: value.__setitem__(
                "version",
                99,
            ),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(encoded)

    def test_envelope_rejects_unknown_field(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        encoded = tamper_envelope(
            envelope.to_base64(),
            lambda value: value.__setitem__(
                "executable",
                "python -c unsafe",
            ),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(encoded)

    def test_envelope_rejects_execution_fingerprint_tamper(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        encoded = tamper_envelope(
            envelope.to_base64(),
            lambda value: value.__setitem__(
                "execution_fingerprint",
                "d" * 64,
            ),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(encoded)

    def test_envelope_rejects_snapshot_fingerprint_tamper(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        encoded = tamper_envelope(
            envelope.to_base64(),
            lambda value: value.__setitem__(
                "snapshot_fingerprint",
                "nope",
            ),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(encoded)

    def test_envelope_rejects_malformed_build_authorization(
        self,
    ) -> None:
        _snap, envelope = self.envelope()
        encoded = tamper_envelope(
            envelope.to_base64(),
            lambda value: value.__setitem__(
                "build_authorization",
                {"version": 1, "issue_number": 1},
            ),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            self.decode(encoded)

    def test_envelope_rejects_non_hex_fingerprint_before_encoding(
        self,
    ) -> None:
        snap = self.snapshot()
        envelope = supervisor.DelegationEnvelope(
            version=3,
            repository=REPO,
            snapshot_fingerprint="z" * 64,
            observed_at=snap.observed_at,
            plan="repair CI",
            execution=EXECUTION,
            build_authorization=None,
        )
        with self.assertRaises(
            supervisor.SupervisorError
        ):
            envelope.to_base64()

    def test_envelope_rejects_empty_plan(
        self,
    ) -> None:
        snap = self.snapshot()
        envelope = supervisor.DelegationEnvelope(
            version=3,
            repository=REPO,
            snapshot_fingerprint=snap.fingerprint,
            observed_at=snap.observed_at,
            plan="",
            execution=EXECUTION,
            build_authorization=None,
        )
        with self.assertRaises(
            supervisor.SupervisorError
        ):
            envelope.to_base64()

    def test_emit_github_output_is_bounded_single_line_data(
        self,
    ) -> None:
        snap, envelope = self.envelope("repair CI")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            supervisor.emit_github_output(
                envelope,
                str(target),
            )
            lines = target.read_text(
                encoding="utf-8"
            ).splitlines()

        self.assertEqual(
            len(lines),
            4,
        )
        self.assertTrue(
            lines[0].startswith("delegation_b64=")
        )
        self.assertEqual(
            lines[1],
            (
                "snapshot_fingerprint="
                f"{snap.fingerprint}"
            ),
        )
        self.assertEqual(
            lines[2],
            (
                "execution_fingerprint="
                f"{EXECUTION.fingerprint}"
            ),
        )
        self.assertEqual(
            lines[3],
            f"base_sha={BASE}",
        )

    def test_emit_github_output_rejects_relative_path(
        self,
    ) -> None:
        _snap, envelope = self.envelope("repair CI")
        with self.assertRaises(
            supervisor.SupervisorError
        ):
            supervisor.emit_github_output(
                envelope,
                "relative-output",
            )

    def test_deterministic_plan_carries_snapshot_identity(
        self,
    ) -> None:
        snap = self.snapshot()
        plan = json.loads(
            supervisor.deterministic_plan(snap)
        )
        self.assertEqual(
            plan["snapshot_fingerprint"],
            snap.fingerprint,
        )
        self.assertEqual(
            plan["priority_observations"][
                "open_issue_count"
            ],
            1,
        )
        self.assertIn(
            "Do not mutate when the observed default-branch "
            "base becomes stale.",
            plan["constraints"],
        )

    def test_model_plan_falls_back_without_complete_provider(
        self,
    ) -> None:
        snap = self.snapshot()
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            self.assertEqual(
                supervisor.model_plan(snap),
                supervisor.deterministic_plan(snap),
            )


    def test_model_plan_delegates_provider_configuration_to_canonical_client(
        self,
    ) -> None:
        snap = self.snapshot()
        with patch.object(
            supervisor,
            "FreeModelClient",
            side_effect=supervisor.ModelError("provider unavailable"),
        ):
            self.assertEqual(
                supervisor.model_plan(snap),
                supervisor.deterministic_plan(snap),
            )


class DurableWorkerHealthTests(unittest.TestCase):
    def test_open_specialist_pr_becomes_durable_health_evidence(self) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(),
            pull_requests=(
                {
                    "number": 17,
                    "headRefName": (
                        "bot/specialist-security-auditor-"
                        "0123456789abcdef"
                    ),
                    "baseRefName": "main",
                    "isDraft": False,
                    "mergeStateStatus": "BLOCKED",
                },
                {
                    "number": 18,
                    "headRefName": "feature/human-work",
                    "baseRefName": "main",
                    "isDraft": False,
                    "mergeStateStatus": "CLEAN",
                },
            ),
            workflow_runs=(),
        )
        health = supervisor.durable_worker_health(snapshot)
        self.assertTrue(health["non_authoritative"])
        self.assertEqual(health["source"], "github-open-pull-requests")
        self.assertEqual(health["active_count"], 1)
        self.assertEqual(
            health["classification_counts"],
            {"awaiting-checks": 1},
        )
        self.assertEqual(
            health["active_workers"],
            [{
                "worker": "security-auditor",
                "pull_request": 17,
                "base_prefix": "0123456789abcdef",
                "merge_state": "BLOCKED",
                "is_draft": False,
                "check_state": "unknown",
                "check_total": 0,
                "check_failures": 0,
                "check_pending": 0,
                "classification": "awaiting-checks",
            }],
        )

    def test_durable_health_uses_canonical_ci_classification(self) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(),
            pull_requests=(
                {
                    "number": 19,
                    "headRefName": (
                        "bot/specialist-security-auditor-"
                        "0123456789abcdef"
                    ),
                    "isDraft": False,
                    "mergeStateStatus": "CLEAN",
                    "statusCheckRollup": [
                        {"status": "COMPLETED", "conclusion": "FAILURE"},
                    ],
                },
            ),
            workflow_runs=(),
        )

        health = supervisor.durable_worker_health(snapshot)

        self.assertEqual(
            health["classification_counts"],
            {"failing-ci": 1},
        )
        self.assertEqual(
            health["active_workers"][0]["classification"],
            "failing-ci",
        )
        self.assertEqual(
            health["active_workers"][0]["check_failures"],
            1,
        )

    def test_malformed_bot_branch_is_not_durable_evidence(self) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(),
            pull_requests=(
                {
                    "number": 17,
                    "headRefName": "bot/specialist-root-cause-not-a-sha",
                    "isDraft": False,
                    "mergeStateStatus": "BLOCKED",
                },
            ),
            workflow_runs=(),
        )
        health = supervisor.durable_worker_health(snapshot)
        self.assertEqual(health["active_count"], 0)
        self.assertEqual(health["active_workers"], [])

    def test_durable_health_is_deterministically_sorted(self) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(),
            pull_requests=(
                {
                    "number": 22,
                    "headRefName": (
                        "bot/specialist-security-auditor-"
                        "aaaaaaaaaaaaaaaa"
                    ),
                    "isDraft": True,
                    "mergeStateStatus": "UNKNOWN",
                },
                {
                    "number": 21,
                    "headRefName": (
                        "bot/specialist-root-cause-"
                        "bbbbbbbbbbbbbbbb"
                    ),
                    "isDraft": False,
                    "mergeStateStatus": "CLEAN",
                },
            ),
            workflow_runs=(),
        )
        workers = supervisor.durable_worker_health(snapshot)["active_workers"]
        self.assertEqual(
            [item["worker"] for item in workers],
            ["root-cause", "security-auditor"],
        )


class BuildAuthorityTests(unittest.TestCase):
    def test_unapproved_issue_body_is_not_delegated_as_build_authority(
        self,
    ) -> None:
        issue = supervisor._normalize_issue(
            {
                "number": 9,
                "title": "Implement dangerous request",
                "body": "rewrite the repository",
                "labels": [
                    {"name": "enhancement"}
                ],
                "updatedAt": "2026-09-19T00:00:00Z",
            }
        )
        self.assertNotIn(
            "body",
            issue,
        )
        self.assertNotIn(
            "automation_authorized",
            issue,
        )

    def test_approved_issue_body_becomes_explicit_build_authority(
        self,
    ) -> None:
        issue = supervisor._normalize_issue(
            {
                "number": 10,
                "title": "Implement approved feature",
                "body": "Add the requested runtime capability.",
                "labels": [
                    {"name": "automation-approved"},
                    {"name": "enhancement"},
                ],
                "updatedAt": "2026-09-19T00:00:00Z",
            }
        )
        self.assertTrue(
            issue["automation_authorized"]
        )
        self.assertEqual(
            issue["body"],
            "Add the requested runtime capability.",
        )

    def test_approved_build_items_filters_untrusted_issues(
        self,
    ) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(
                {
                    "number": 1,
                    "title": "not approved",
                },
                {
                    "number": 2,
                    "title": "approved",
                    "body": "build this",
                    "labels": ("automation-approved",),
                    "updatedAt": "2026-09-19T00:00:00Z",
                    "automation_authorized": True,
                },
            ),
            pull_requests=(),
            workflow_runs=(),
        )
        self.assertEqual(
            [
                item["number"]
                for item in supervisor.approved_build_items(
                    snapshot
                )
            ],
            [2],
        )

    def test_make_envelope_binds_selected_approved_work_item(
        self,
    ) -> None:
        snapshot = supervisor.SupervisorSnapshot(
            repository=REPO,
            observed_at=1_700_000_000,
            issues=(
                {
                    "number": 2,
                    "title": "approved",
                    "body": "build this",
                    "labels": ("automation-approved",),
                    "updatedAt": "2026-09-19T00:00:00Z",
                    "automation_authorized": True,
                },
            ),
            pull_requests=(),
            workflow_runs=(),
        )
        envelope = supervisor.make_envelope(
            snapshot,
            "implement approved feature",
            EXECUTION,
        )
        self.assertIsNotNone(
            envelope.build_authorization,
        )
        self.assertEqual(
            envelope.build_authorization.issue_number,
            2,
        )
        decoded = secretary.decode_delegation(
            envelope.to_base64(),
            repository=REPO,
            expected_execution=EXECUTION,
            now=snapshot.observed_at,
        )
        self.assertIsNotNone(
            decoded[3],
        )
        self.assertEqual(
            decoded[3].issue_number,
            2,
        )

    def test_feature_builder_is_inert_without_approved_work(
        self,
    ) -> None:
        routed = secretary.route(
            (
                "approved_work_items automation_authorized "
                "feature implement enhancement"
            ),
            ["feature-builder"],
            build_authorization=None,
        )
        self.assertEqual(
            routed,
            [],
        )

    def test_feature_builder_routes_only_with_approved_work(
        self,
    ) -> None:
        routed = secretary.route(
            (
                "approved_work_items automation_authorized "
                "feature implement enhancement"
            ),
            ["feature-builder"],
            build_authorization=supervisor.selected_build_authorization(
                supervisor.SupervisorSnapshot(
                    repository=REPO,
                    observed_at=1_700_000_000,
                    issues=(
                        {
                            "number": 9,
                            "title": "approved",
                            "body": "implement this",
                            "labels": ("automation-approved",),
                            "updatedAt": "2026-09-19T00:00:00Z",
                            "automation_authorized": True,
                        },
                    ),
                    pull_requests=(),
                    workflow_runs=(),
                )
            ),
        )
        self.assertEqual(
            routed,
            ["feature-builder"],
        )

    def test_authorized_feature_builder_is_not_suppressed_by_plan_text(
        self,
    ) -> None:
        routed = secretary.route(
            "CI workflow failure",
            [
                "root-cause",
                "feature-builder",
            ],
            build_authorization=supervisor.selected_build_authorization(
                supervisor.SupervisorSnapshot(
                    repository=REPO,
                    observed_at=1_700_000_000,
                    issues=(
                        {
                            "number": 9,
                            "title": "approved",
                            "body": "implement this",
                            "labels": ("automation-approved",),
                            "updatedAt": "2026-09-19T00:00:00Z",
                            "automation_authorized": True,
                        },
                    ),
                    pull_requests=(),
                    workflow_runs=(),
                )
            ),
        )
        self.assertEqual(routed, ["feature-builder", "root-cause"])


class SecretaryRoutingTests(unittest.TestCase):
    def test_route_only_returns_due_registered_workers(
        self,
    ) -> None:
        due = [
            "root-cause",
            "security-auditor",
        ]
        self.assertEqual(
            set(
                secretary.route(
                    "CI build failure and security finding",
                    due,
                )
            ),
            set(due),
        )

    def test_route_ignores_unregistered_due_names(
        self,
    ) -> None:
        self.assertEqual(
            secretary.route(
                "CI build failure",
                [
                    "root-cause",
                    "arbitrary-module",
                ],
            ),
            ["root-cause"],
        )

    def test_route_never_exceeds_assignment_budget(
        self,
    ) -> None:
        due = [
            spec.name
            for spec in secretary.ADVANCED_BOTS
        ]
        routed = secretary.route(
            (
                "CI workflow failure dependency CVE regression "
                "architecture security performance release docs "
                "integration contract PR review coverage API schema"
            ),
            due,
        )
        self.assertLessEqual(
            len(routed),
            secretary.MAX_ASSIGNMENTS,
        )

    def test_dispatch_rejects_duplicate_workers(
        self,
    ) -> None:
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "plan",
                [
                    "root-cause",
                    "root-cause",
                ],
                FP,
                EXECUTION,
            )

    def test_dispatch_rejects_unregistered_worker(
        self,
    ) -> None:
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "plan",
                ["arbitrary-module"],
                FP,
                EXECUTION,
            )

    def test_dispatch_rejects_assignment_budget_overflow(
        self,
    ) -> None:
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "plan",
                [
                    spec.name
                    for spec
                    in secretary.ADVANCED_BOTS[:4]
                ],
                FP,
                EXECUTION,
            )

    def test_dispatch_rejects_invalid_snapshot_fingerprint(
        self,
    ) -> None:
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "plan",
                ["root-cause"],
                "bad",
                EXECUTION,
            )

    def test_dispatch_uses_isolated_worker_boundary(
        self,
    ) -> None:
        with patch(
            "skeleton.automation.secretary._dispatch_one",
            return_value={
                "bot": "root-cause",
                "returncode": 0,
                "isolated": True,
            },
        ) as worker:
            result = secretary.dispatch(
                "CI failure",
                ["root-cause"],
                FP,
                EXECUTION,
            )

        self.assertEqual(result[0]["bot"], "root-cause")
        self.assertEqual(result[0]["returncode"], 0)
        self.assertTrue(result[0]["isolated"])
        self.assertEqual(len(result[0]["attempt_history"]), 1)
        self.assertEqual(len(result[0]["retry_chain_digest"]), 64)
        worker.assert_called_once_with(
            "CI failure",
            "root-cause",
            supervisor_fingerprint=FP,
            execution=EXECUTION,
            build_authorization=None,
            attempt=1,
        )


class WorkerAdmissionTests(unittest.TestCase):
    def test_direct_worker_invocation_is_rejected(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_worker(
                    "root-cause"
                )

    def test_worker_identity_mismatch_is_rejected(
        self,
    ) -> None:
        env = execution_env(
            worker="security-auditor"
        )
        with patch.dict(
            os.environ,
            env,
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_worker(
                    "root-cause"
                )

    def test_worker_execution_fingerprint_mismatch_is_rejected(
        self,
    ) -> None:
        env = execution_env()
        env[
            "SUPERVISOR_EXECUTION_FINGERPRINT"
        ] = "d" * 64
        with patch.dict(
            os.environ,
            env,
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_worker(
                    "root-cause"
                )

    def test_valid_secretary_delegation_returns_full_custody(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            execution_env(),
            clear=True,
        ):
            custody = specialist_bots.admit_worker(
                "root-cause"
            )

        self.assertIsInstance(
            custody,
            WorkerCustody,
        )
        self.assertEqual(
            custody.worker,
            "root-cause",
        )
        self.assertEqual(
            custody.snapshot_fingerprint,
            FP,
        )
        self.assertEqual(
            custody.execution,
            EXECUTION,
        )

    def test_retry_token_replay_under_different_attempt_is_rejected(self) -> None:
        env = execution_env()
        env["SECRETARY_ATTEMPT"] = "2"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(specialist_bots.WorkerAdmissionError):
                specialist_bots.admit_worker("root-cause")

    def test_retry_token_tamper_is_rejected(self) -> None:
        env = execution_env()
        env["SECRETARY_RETRY_TOKEN"] = "f" * 64
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(specialist_bots.WorkerAdmissionError):
                specialist_bots.admit_worker("root-cause")

    def test_feature_builder_rejects_duplicate_authorization_keys(
        self,
    ) -> None:
        authorization = BuildAuthorization.from_issue(
            REPO,
            {
                "number": 17,
                "title": "Approved build",
                "body": "Implement the bounded task.",
                "labels": ["automation-approved"],
                "updatedAt": "2026-09-19T00:00:00Z",
                "automation_authorized": True,
            },
        )
        rendered = json.dumps(
            authorization.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        rendered = rendered.replace(
            '"version":1',
            '"version":1,"version":1',
            1,
        )
        env = execution_env(worker="feature-builder")
        env["SUPERVISOR_BUILD_AUTHORIZATION_B64"] = (
            base64.b64encode(rendered.encode("utf-8")).decode("ascii")
        )
        env["SUPERVISOR_BUILD_TASK_DIGEST"] = authorization.task_digest
        custody = WorkerCustody(
            worker="feature-builder",
            snapshot_fingerprint=FP,
            execution=EXECUTION,
        )
        with patch.dict(
            os.environ,
            env,
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_build_authorization(custody)

    def test_invalid_supervisor_fingerprint_is_rejected(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            execution_env(snapshot="bad"),
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_worker(
                    "root-cause"
                )


class WorkerPublicationBoundaryTests(unittest.TestCase):
    def test_publication_env_rebuilds_fixed_git_identity(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "token",
                "GH_TOKEN": "shadow",
                "GIT_AUTHOR_NAME": "attacker",
                "GIT_AUTHOR_EMAIL": "attacker@example.invalid",
                "GIT_COMMITTER_NAME": "attacker",
                "GIT_COMMITTER_EMAIL": "attacker@example.invalid",
                "MODEL_API_KEY": "model-secret",
            },
            clear=True,
        ):
            env = specialist_bots._publication_env()

        self.assertEqual(env["GITHUB_TOKEN"], "token")
        self.assertEqual(env["GH_TOKEN"], "token")
        self.assertEqual(
            env["GIT_AUTHOR_NAME"],
            "skeleton-specialist-bot",
        )
        self.assertEqual(
            env["GIT_COMMITTER_NAME"],
            "skeleton-specialist-bot",
        )
        self.assertEqual(
            env["GIT_AUTHOR_EMAIL"],
            "skeleton-specialist-bot@users.noreply.github.com",
        )
        self.assertEqual(
            env["GIT_COMMITTER_EMAIL"],
            "skeleton-specialist-bot@users.noreply.github.com",
        )
        self.assertNotIn("MODEL_API_KEY", env)

    def test_hook_suppression_is_scoped_to_one_git_invocation(self) -> None:
        hooks = Path("/tmp/empty-hooks")
        self.assertEqual(
            specialist_bots._hookless_git_args(
                hooks,
                "push",
                "--set-upstream",
                "origin",
                "bot/specialist-root-cause-aaaaaaaaaaaaaaaa",
            ),
            [
                "-c",
                "core.hooksPath=/tmp/empty-hooks",
                "push",
                "--set-upstream",
                "origin",
                "bot/specialist-root-cause-aaaaaaaaaaaaaaaa",
            ],
        )


class WorkerProposalTests(unittest.TestCase):
    def test_safe_path_rejects_control_planes(
        self,
    ) -> None:
        self.assertFalse(
            specialist_bots.safe_path(
                ".github/workflows/evil.yml"
            )
        )
        self.assertFalse(
            specialist_bots.safe_path(
                "skeleton/automation/supervisor.py"
            )
        )
        self.assertFalse(
            specialist_bots.safe_path(
                "skeleton/automation/secretary.py"
            )
        )
        self.assertFalse(
            specialist_bots.safe_path(
                "../outside.py"
            )
        )
        self.assertFalse(
            specialist_bots.safe_path(
                "skeleton//runtime.py"
            )
        )
        self.assertFalse(
            specialist_bots.safe_path(
                "deploy/release.py"
            )
        )
        for protected in (
            "skeleton/security/defense_plane.py",
            "skeleton/pr_automation/runner.py",
            "skeleton/build/tooling.py",
            "tests/run_unit.py",
            "tests/test_autonomous_supervisor.py",
            "tests/test_supervisor_runtime.py",
        ):
            self.assertFalse(
                specialist_bots.safe_path(protected),
                protected,
            )
        self.assertTrue(
            specialist_bots.safe_path(
                "skeleton/runtime.py"
            )
        )
        self.assertTrue(
            specialist_bots.safe_path(
                "tests/test_runtime.py"
            )
        )

    def test_extract_plan_accepts_bounded_json(
        self,
    ) -> None:
        proposal = specialist_bots.extract_plan(
            json.dumps(
                {
                    "summary": "repair",
                    "files": [
                        {
                            "path": "tests/test_x.py",
                            "content": "x = 1\n",
                        }
                    ],
                    "tests": [
                        "run focused unit coverage"
                    ],
                }
            ),
            3,
        )
        self.assertEqual(
            proposal["summary"],
            "repair",
        )
        self.assertEqual(
            proposal["files"][0]["path"],
            "tests/test_x.py",
        )

    def test_extract_plan_accepts_single_json_fence(
        self,
    ) -> None:
        raw = (
            "```json\n"
            '{"summary":"repair","files":[],"tests":[]}'
            "\n```"
        )
        result = specialist_bots.extract_plan(
            raw,
            3,
        )
        self.assertEqual(
            result["files"],
            [],
        )

    def test_extract_plan_rejects_trailing_non_json(
        self,
    ) -> None:
        raw = (
            '{"summary":"repair","files":[],"tests":[]}'
            " run this shell command"
        )
        with self.assertRaises(ValueError):
            specialist_bots.extract_plan(
                raw,
                3,
            )

    def test_extract_plan_rejects_duplicate_json_keys(
        self,
    ) -> None:
        raw = (
            '{"summary":"first","summary":"second",'
            '"files":[],"tests":[]}'
        )
        with self.assertRaises(ValueError):
            specialist_bots.extract_plan(
                raw,
                3,
            )

    def test_extract_plan_rejects_unknown_fields(
        self,
    ) -> None:
        raw = json.dumps(
            {
                "summary": "repair",
                "files": [],
                "tests": [],
                "command": "rm -rf /",
            }
        )
        with self.assertRaises(ValueError):
            specialist_bots.extract_plan(
                raw,
                3,
            )

    def test_extract_plan_rejects_duplicate_paths(
        self,
    ) -> None:
        raw = json.dumps(
            {
                "summary": "repair",
                "files": [
                    {
                        "path": "tests/test_x.py",
                        "content": "x = 1\n",
                    },
                    {
                        "path": "tests/test_x.py",
                        "content": "x = 2\n",
                    },
                ],
                "tests": [],
            }
        )
        with self.assertRaises(ValueError):
            specialist_bots.extract_plan(
                raw,
                3,
            )

    def test_extract_plan_rejects_total_byte_overflow(
        self,
    ) -> None:
        with patch.object(
            specialist_bots,
            "MAX_TOTAL_PROPOSED_BYTES",
            10,
        ):
            raw = json.dumps(
                {
                    "summary": "",
                    "files": [
                        {
                            "path": "tests/test_x.py",
                            "content": "x" * 11,
                        }
                    ],
                    "tests": [],
                }
            )
            with self.assertRaises(ValueError):
                specialist_bots.extract_plan(
                    raw,
                    3,
                )

    def test_extract_plan_rejects_oversized_test_metadata(
        self,
    ) -> None:
        with patch.object(
            specialist_bots,
            "MAX_TEST_DESCRIPTION_BYTES",
            5,
        ):
            raw = json.dumps(
                {
                    "summary": "",
                    "files": [],
                    "tests": [
                        "too-long-description"
                    ],
                }
            )
            with self.assertRaises(ValueError):
                specialist_bots.extract_plan(
                    raw,
                    3,
                )

    def test_generated_python_must_parse(
        self,
    ) -> None:
        with self.assertRaises(RuntimeError):
            specialist_bots.validate_generated_files(
                [
                    {
                        "path": "tests/test_bad.py",
                        "content": "def broken(:\n",
                    }
                ]
            )

    def test_generated_json_must_parse(
        self,
    ) -> None:
        with self.assertRaises(RuntimeError):
            specialist_bots.validate_generated_files(
                [
                    {
                        "path": "docs/result.json",
                        "content": "{broken",
                    }
                ]
            )

    def test_mutation_budget_counts_insertions_and_deletions(
        self,
    ) -> None:
        files = [
            {
                "path": "tests/test_x.py",
                "content": "new\nvalue\n",
            }
        ]
        with patch(
            "skeleton.automation.specialist_bots._head_text",
            return_value="old\n",
        ):
            self.assertEqual(
                specialist_bots.validate_mutation_budget(
                    files
                ),
                3,
            )

    def test_mutation_budget_fails_closed(
        self,
    ) -> None:
        files = [
            {
                "path": "tests/test_x.py",
                "content": "a\nb\nc\n",
            }
        ]
        with (
            patch.object(
                specialist_bots,
                "MAX_CHANGED_LINES",
                2,
            ),
            patch(
                "skeleton.automation.specialist_bots._head_text",
                return_value="",
            ),
        ):
            with self.assertRaises(RuntimeError):
                specialist_bots.validate_mutation_budget(
                    files
                )

    def test_noop_files_are_removed(
        self,
    ) -> None:
        files = [
            {
                "path": "tests/test_x.py",
                "content": "same\n",
            },
            {
                "path": "tests/test_y.py",
                "content": "new\n",
            },
        ]

        def old(path: str):
            if path.endswith("test_x.py"):
                return "same\n"
            return "old\n"

        with patch(
            "skeleton.automation.specialist_bots._head_text",
            side_effect=old,
        ):
            result = specialist_bots.filter_noop_files(
                files
            )

        self.assertEqual(
            [item["path"] for item in result],
            ["tests/test_y.py"],
        )

    def test_preflight_converges_on_existing_worker_pr(
        self,
    ) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=EXECUTION,
        )
        existing = {
            "number": 77,
            "headRefName": (
                "bot/specialist-root-cause-aaaaaaaaaaaaaaaa"
            ),
            "baseRefName": "main",
        }
        with (
            patch(
                "skeleton.automation.specialist_bots.require_exact_head"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_clean_worktree"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_remote_base_unchanged"
            ),
            patch(
                "skeleton.automation.specialist_bots.find_open_pr_for_worker",
                return_value=existing,
            ),
        ):
            _branch, active = specialist_bots._preflight(
                custody
            )

        self.assertEqual(
            active,
            existing,
        )

    def test_preflight_rejects_worker_pr_on_unexpected_base(
        self,
    ) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=EXECUTION,
        )
        existing = {
            "number": 77,
            "headRefName": (
                "bot/specialist-root-cause-aaaaaaaaaaaaaaaa"
            ),
            "baseRefName": "release",
        }
        with (
            patch(
                "skeleton.automation.specialist_bots.require_exact_head"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_clean_worktree"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_remote_base_unchanged"
            ),
            patch(
                "skeleton.automation.specialist_bots.find_open_pr_for_worker",
                return_value=existing,
            ),
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots._preflight(custody)

    def test_preflight_rejects_orphan_remote_branch(
        self,
    ) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=FP,
            execution=EXECUTION,
        )
        with (
            patch(
                "skeleton.automation.specialist_bots.require_exact_head"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_clean_worktree"
            ),
            patch(
                "skeleton.automation.specialist_bots.require_remote_base_unchanged"
            ),
            patch(
                "skeleton.automation.specialist_bots.find_open_pr_for_worker",
                return_value=None,
            ),
            patch(
                "skeleton.automation.specialist_bots.find_open_pr_for_head",
                return_value=None,
            ),
            patch(
                "skeleton.automation.specialist_bots.remote_branch_exists",
                return_value=True,
            ),
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots._preflight(
                    custody
                )


class AutonomousPublicationEvidenceTests(unittest.TestCase):
    def test_worker_publication_requests_and_surfaces_pull_request_url(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "skeleton"
            / "automation"
            / "specialist_bots.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"pull_request_url"', source)
        self.assertIn('"--json"', source)
        self.assertIn('"number,url"', source)
        self.assertRegex(
            source,
            r'"gh",\s*"pr",\s*"create"',
        )


if __name__ == "__main__":
    unittest.main()
