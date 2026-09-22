from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from skeleton.automation import secretary, specialist_bots
from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.builder_plane import (
    BuilderBudget,
    BuilderManifest,
    BuilderPlaneError,
    BuilderProposalReceipt,
    builder_worker_branch,
    compile_builder_manifest,
    compile_builder_proposal_receipt,
    validate_builder_custody,
    validate_builder_proposal_receipt,
    validate_builder_worker_evidence,
)
from skeleton.automation.supervisor_runtime import (
    ExecutionIdentity,
    SupervisorRuntimeError,
    WorkerCustody,
    parse_worker_result,
    validate_worker_evidence_custody,
)


REPO = "Apeloff1/Skeleton"
BASE = "a" * 40
SNAPSHOT = "b" * 64


def execution(*, run_id: str = "100") -> ExecutionIdentity:
    return ExecutionIdentity(
        repository=REPO,
        base_sha=BASE,
        default_branch="main",
        run_id=run_id,
        run_attempt="1",
    )


def authorization() -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        {
            "number": 77,
            "title": "Build typed integration capability",
            "body": (
                "Implement the integration contract with regression tests "
                "and documentation."
            ),
            "labels": (
                "automation-approved",
                "enhancement",
                "integration",
            ),
            "updatedAt": "2026-09-20T03:00:00Z",
            "automation_authorized": True,
        },
    )


def manifest(
    *,
    snapshot: str = SNAPSHOT,
    run: ExecutionIdentity | None = None,
) -> BuilderManifest:
    return compile_builder_manifest(
        authorization(),
        snapshot_fingerprint=snapshot,
        execution=run or execution(),
    )


def proposal_receipt(
    value: BuilderManifest | None = None,
) -> BuilderProposalReceipt:
    current = value or manifest()
    return compile_builder_proposal_receipt(
        current,
        proposal_digest="c" * 64,
        branch=builder_worker_branch(current),
        files=(
            {
                "path": "skeleton/feature.py",
                "content": "VALUE = 1\n",
            },
        ),
        tests=("focused regression",),
        changed_lines=12,
    )


def feature_custody() -> WorkerCustody:
    return WorkerCustody(
        worker="feature-builder",
        snapshot_fingerprint=SNAPSHOT,
        execution=execution(),
    )


class SecretaryBuilderPlaneIntegrationTests(unittest.TestCase):
    def test_secretary_imports_worker_custody_for_evidence_validation(self) -> None:
        self.assertIs(secretary.WorkerCustody, WorkerCustody)

    def test_feature_dispatch_compiles_manifest_before_worker_boundary(self) -> None:
        auth = authorization()
        with patch(
            "skeleton.automation.secretary._dispatch_one",
            return_value={
                "bot": "feature-builder",
                "returncode": 0,
                "isolated": True,
            },
        ) as worker:
            result = secretary.dispatch(
                "approved_work_items feature implement enhancement",
                ["feature-builder"],
                SNAPSHOT,
                execution(),
                build_authorization=auth,
            )

        self.assertEqual(result[0]["returncode"], 0)
        worker.assert_called_once()
        kwargs = worker.call_args.kwargs
        compiled = kwargs["builder_manifest"]
        self.assertIsInstance(compiled, BuilderManifest)
        validate_builder_custody(
            compiled,
            authorization=auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(
            compiled.task_digest,
            auth.task_digest,
        )

    def test_non_feature_dispatch_does_not_gain_builder_manifest(self) -> None:
        with patch(
            "skeleton.automation.secretary._dispatch_one",
            return_value={
                "bot": "root-cause",
                "returncode": 0,
                "isolated": True,
            },
        ) as worker:
            secretary.dispatch(
                "CI workflow failure",
                ["root-cause"],
                SNAPSHOT,
                execution(),
            )

        self.assertNotIn(
            "builder_manifest",
            worker.call_args.kwargs,
        )
        self.assertIsNone(
            worker.call_args.kwargs["build_authorization"],
        )

    def test_feature_dispatch_rejects_manifest_from_different_snapshot(self) -> None:
        auth = authorization()
        wrong = compile_builder_manifest(
            auth,
            snapshot_fingerprint="c" * 64,
            execution=execution(),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "approved_work_items feature implement enhancement",
                ["feature-builder"],
                SNAPSHOT,
                execution(),
                build_authorization=auth,
                builder_manifest=wrong,
            )

    def test_feature_dispatch_rejects_manifest_from_different_execution(self) -> None:
        auth = authorization()
        wrong = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(run_id="999"),
        )
        with self.assertRaises(
            secretary.SecretaryAdmissionError
        ):
            secretary.dispatch(
                "approved_work_items feature implement enhancement",
                ["feature-builder"],
                SNAPSHOT,
                execution(),
                build_authorization=auth,
                builder_manifest=wrong,
            )


class FeatureBuilderPreflightTests(unittest.TestCase):
    def test_matching_task_branch_converges_on_existing_pr(self) -> None:
        value = manifest()
        expected_branch = builder_worker_branch(value)
        active = {
            "number": 91,
            "headRefName": expected_branch,
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
                return_value=active,
            ),
        ):
            branch, selected = specialist_bots._preflight(
                feature_custody(),
                builder_manifest=value,
            )
        self.assertEqual(branch, expected_branch)
        self.assertEqual(selected, active)

    def test_different_task_pr_on_same_base_fails_closed(self) -> None:
        value = manifest()
        active = {
            "number": 92,
            "headRefName": (
                "bot/specialist-feature-builder-" + ("f" * 16)
            ),
            "baseRefName": "main",
        }
        self.assertNotEqual(
            active["headRefName"],
            builder_worker_branch(value),
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
                return_value=active,
            ),
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots._preflight(
                    feature_custody(),
                    builder_manifest=value,
                )


class WorkerLiveAuthorityRebindTests(unittest.TestCase):
    def test_exact_live_authority_rebind_is_accepted(self) -> None:
        auth = authorization()
        value = manifest()
        with patch(
            "skeleton.automation.specialist_bots."
            "revalidate_live_build_authorization",
            return_value=auth,
        ) as live:
            current = specialist_bots.revalidate_builder_authority(
                feature_custody(),
                auth,
                value,
            )
        self.assertEqual(current, auth)
        live.assert_called_once_with(auth)

    def test_changed_live_authority_fails_closed(self) -> None:
        auth = authorization()
        changed = BuildAuthorization.from_issue(
            REPO,
            {
                "number": 77,
                "title": "Build typed integration capability",
                "body": "Implement a changed task with regression tests.",
                "labels": (
                    "automation-approved",
                    "enhancement",
                    "integration",
                ),
                "updatedAt": "2026-09-20T03:01:00Z",
                "automation_authorized": True,
            },
        )
        with patch(
            "skeleton.automation.specialist_bots."
            "revalidate_live_build_authorization",
            return_value=changed,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.revalidate_builder_authority(
                    feature_custody(),
                    auth,
                    manifest(),
                )

    def test_manifestless_feature_revalidation_is_rejected(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.revalidate_builder_authority(
                feature_custody(),
                authorization(),
                None,
            )

    def test_non_builder_cannot_receive_build_authority(self) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.revalidate_builder_authority(
                custody,
                authorization(),
                manifest(),
            )

    def test_non_builder_without_authority_remains_inert(self) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertIsNone(
            specialist_bots.revalidate_builder_authority(
                custody,
                None,
                None,
            )
        )


class WorkerManifestAdmissionTests(unittest.TestCase):
    def admitted_env(
        self,
        value: BuilderManifest,
    ) -> dict[str, str]:
        return {
            "SUPERVISOR_BUILDER_MANIFEST_B64": value.to_base64(),
            "SUPERVISOR_BUILDER_MANIFEST_DIGEST": value.manifest_digest,
        }

    def test_feature_worker_accepts_exact_builder_manifest(self) -> None:
        value = manifest()
        with patch.dict(
            os.environ,
            self.admitted_env(value),
            clear=True,
        ):
            admitted = specialist_bots.admit_builder_manifest(
                feature_custody(),
                authorization(),
            )
        self.assertEqual(admitted, value)

    def test_feature_worker_rejects_missing_builder_manifest(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_builder_manifest(
                    feature_custody(),
                    authorization(),
                )

    def test_feature_worker_rejects_manifest_digest_tamper(self) -> None:
        value = manifest()
        env = self.admitted_env(value)
        env["SUPERVISOR_BUILDER_MANIFEST_DIGEST"] = "0" * 64
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_builder_manifest(
                    feature_custody(),
                    authorization(),
                )

    def test_feature_worker_rejects_manifest_snapshot_tamper(self) -> None:
        wrong = manifest(snapshot="c" * 64)
        with patch.dict(
            os.environ,
            self.admitted_env(wrong),
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_builder_manifest(
                    feature_custody(),
                    authorization(),
                )

    def test_non_builder_worker_rejects_manifest_leak(self) -> None:
        value = manifest()
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with patch.dict(
            os.environ,
            self.admitted_env(value),
            clear=True,
        ):
            with self.assertRaises(
                specialist_bots.WorkerAdmissionError
            ):
                specialist_bots.admit_builder_manifest(
                    custody,
                    None,
                )

    def test_non_builder_worker_without_manifest_remains_inert(self) -> None:
        custody = WorkerCustody(
            worker="root-cause",
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(
                specialist_bots.admit_builder_manifest(
                    custody,
                    None,
                )
            )


class WorkerBuilderPromptTests(unittest.TestCase):
    def feature_spec(self):
        return specialist_bots.spec_for("feature-builder")

    def root_spec(self):
        return specialist_bots.spec_for("root-cause")

    def test_feature_prompt_contains_manifest_digest_and_stages(self) -> None:
        value = manifest()
        prompt = specialist_bots._render_prompt(
            self.feature_spec(),
            REPO,
            "approved feature task",
            build_authorization=authorization(),
            builder_manifest=value,
        )
        self.assertIn(value.manifest_digest, prompt)
        self.assertIn('"stages"', prompt)
        self.assertIn('"budget"', prompt)
        self.assertIn('"mutation_allowed":true', prompt)
        self.assertIn("Only the implement stage permits", prompt)

    def test_feature_prompt_rejects_missing_manifest(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots._render_prompt(
                self.feature_spec(),
                REPO,
                "approved feature task",
                build_authorization=authorization(),
                builder_manifest=None,
            )

    def test_non_builder_prompt_rejects_manifest_leak(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots._render_prompt(
                self.root_spec(),
                REPO,
                "CI failure",
                builder_manifest=manifest(),
            )

    def test_manifest_prompt_is_inert_json_not_shell(self) -> None:
        prompt = specialist_bots._render_prompt(
            self.feature_spec(),
            REPO,
            "approved feature task",
            build_authorization=authorization(),
            builder_manifest=manifest(),
        )
        marker = "BUILDER PLANE MANIFEST (inert deterministic constraints):\n"
        fragment = prompt.split(marker, 1)[1].split(
            "\nThe Builder Plane stages",
            1,
        )[0]
        payload = json.loads(fragment)
        self.assertNotIn("command", payload)
        self.assertNotIn("executable", payload)
        self.assertNotIn("workflow", payload)
        self.assertNotIn("permission", payload)


class WorkerBuilderRegressionPolicyTests(unittest.TestCase):
    def test_feature_builder_registry_requires_tests(self) -> None:
        self.assertTrue(
            specialist_bots.spec_for("feature-builder").requires_tests
        )

    def test_non_documentation_build_requires_regression_intent(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_regression_policy(
                {
                    "summary": "implementation",
                    "files": [
                        {
                            "path": "skeleton/feature.py",
                            "content": "VALUE = 1\n",
                        }
                    ],
                    "tests": [],
                },
                specialist_bots.spec_for("feature-builder"),
                manifest(),
            )

    def test_non_documentation_build_accepts_bounded_regression_intent(
        self,
    ) -> None:
        specialist_bots.validate_builder_regression_policy(
            {
                "summary": "implementation",
                "files": [
                    {
                        "path": "skeleton/feature.py",
                        "content": "VALUE = 1\n",
                    }
                ],
                "tests": ["exercise the authorized feature behavior"],
            },
            specialist_bots.spec_for("feature-builder"),
            manifest(),
        )

    def test_empty_regression_intent_entry_is_rejected(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_regression_policy(
                {
                    "summary": "implementation",
                    "files": [
                        {
                            "path": "skeleton/feature.py",
                            "content": "VALUE = 1\n",
                        }
                    ],
                    "tests": ["   "],
                },
                specialist_bots.spec_for("feature-builder"),
                manifest(),
            )

    def test_pure_documentation_build_does_not_invent_tests(self) -> None:
        auth = BuildAuthorization.from_issue(
            REPO,
            {
                "number": 88,
                "title": "Update documentation guide",
                "body": "Refresh documentation guide wording only.",
                "labels": ("automation-approved",),
                "updatedAt": "2026-09-20T03:10:00Z",
                "automation_authorized": True,
            },
        )
        docs_manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(
            docs_manifest.signals,
            ("documentation",),
        )
        specialist_bots.validate_builder_regression_policy(
            {
                "summary": "docs only",
                "files": [
                    {
                        "path": "docs/guide.md",
                        "content": "Updated guide.\n",
                    }
                ],
                "tests": [],
            },
            specialist_bots.spec_for("feature-builder"),
            docs_manifest,
        )

    def test_regression_policy_rejects_non_builder_specialist(self) -> None:
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_regression_policy(
                {
                    "summary": "irrelevant",
                    "files": [],
                    "tests": [],
                },
                specialist_bots.spec_for("root-cause"),
                manifest(),
            )


class WorkerBuilderBudgetTests(unittest.TestCase):
    def test_file_budget_is_enforced_before_write(self) -> None:
        value = replace(
            manifest(),
            budget=BuilderBudget(
                max_files=1,
                max_changed_lines=1200,
                max_total_bytes=240_000,
                max_test_descriptions=12,
            ),
        )
        result = {
            "summary": "two files",
            "files": [
                {"path": "skeleton/a.py", "content": "a"},
                {"path": "skeleton/b.py", "content": "b"},
            ],
            "tests": [],
        }
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_proposal_budget(
                result,
                value,
            )

    def test_test_description_budget_is_enforced(self) -> None:
        value = replace(
            manifest(),
            budget=BuilderBudget(
                max_files=10,
                max_changed_lines=1200,
                max_total_bytes=240_000,
                max_test_descriptions=1,
            ),
        )
        result = {
            "summary": "tests",
            "files": [],
            "tests": ["one", "two"],
        }
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_proposal_budget(
                result,
                value,
            )

    def test_byte_budget_is_enforced_before_write(self) -> None:
        value = replace(
            manifest(),
            budget=BuilderBudget(
                max_files=10,
                max_changed_lines=1200,
                max_total_bytes=10,
                max_test_descriptions=12,
            ),
        )
        result = {
            "summary": "bytes",
            "files": [
                {
                    "path": "skeleton/feature.py",
                    "content": "x" * 100,
                }
            ],
            "tests": [],
        }
        with self.assertRaises(
            specialist_bots.WorkerAdmissionError
        ):
            specialist_bots.validate_builder_proposal_budget(
                result,
                value,
            )

    def test_valid_bounded_proposal_is_accepted(self) -> None:
        value = manifest()
        result = {
            "summary": "bounded",
            "files": [
                {
                    "path": "skeleton/feature.py",
                    "content": "VALUE = 1\n",
                }
            ],
            "tests": ["focused regression"],
        }
        specialist_bots.validate_builder_proposal_budget(
            result,
            value,
        )



class BuilderWorkerEvidenceTests(unittest.TestCase):
    def created_evidence(
        self,
        *,
        digest: str | None = None,
        bot: str = "feature-builder",
        branch: str | None = None,
        task_digest: str | None = None,
        issue_number: int | None = None,
    ) -> dict[str, object]:
        value = manifest()
        return {
            "status": "pull-request-created",
            "bot": bot,
            "branch": (
                builder_worker_branch(value)
                if branch is None
                else branch
            ),
            "changed_lines": 12,
            "proposal_digest": "c" * 64,
            "base_sha": BASE,
            "supervisor_snapshot_fingerprint": SNAPSHOT,
            "execution_fingerprint": execution().fingerprint,
            "build_issue_number": (
                value.issue_number
                if issue_number is None
                else issue_number
            ),
            "build_task_digest": (
                value.task_digest
                if task_digest is None
                else task_digest
            ),
            "builder_manifest_digest": (
                value.manifest_digest if digest is None else digest
            ),
            "builder_proposal_receipt": (
                proposal_receipt(value).as_dict()
            ),
        }

    def existing_evidence(
        self,
        *,
        branch: str | None = None,
        task_digest: str | None = None,
        issue_number: int | None = None,
    ) -> dict[str, object]:
        value = manifest()
        return {
            "status": "existing-pr",
            "bot": "feature-builder",
            "branch": (
                builder_worker_branch(value)
                if branch is None
                else branch
            ),
            "pull_request": 93,
            "supervisor_snapshot_fingerprint": SNAPSHOT,
            "build_issue_number": (
                value.issue_number
                if issue_number is None
                else issue_number
            ),
            "build_task_digest": (
                value.task_digest
                if task_digest is None
                else task_digest
            ),
        }

    def updated_evidence(
        self,
        *,
        repair_parent_sha: str = "d" * 40,
    ) -> dict[str, object]:
        value = self.created_evidence()
        value["status"] = "pull-request-updated"
        value["pull_request"] = 93
        value["repair_parent_sha"] = repair_parent_sha
        return value

    def test_updated_pr_evidence_is_receipt_and_manifest_bound(self) -> None:
        value = manifest()
        evidence = parse_worker_result(
            json.dumps(self.updated_evidence()),
            worker="feature-builder",
        )
        self.assertEqual(
            evidence["repair_parent_sha"],
            "d" * 40,
        )
        validate_worker_evidence_custody(
            evidence,
            feature_custody(),
            expected_branch=builder_worker_branch(value),
        )
        validate_builder_worker_evidence(
            evidence,
            value,
        )

    def test_updated_pr_evidence_requires_repair_parent(self) -> None:
        evidence = self.updated_evidence()
        evidence.pop("repair_parent_sha")
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(evidence),
                worker="feature-builder",
            )

    def test_updated_pr_evidence_rejects_invalid_repair_parent(self) -> None:
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(
                    self.updated_evidence(
                        repair_parent_sha="not-a-sha"
                    )
                ),
                worker="feature-builder",
            )

    def test_runtime_parser_retains_manifest_digest(self) -> None:
        payload = json.dumps(self.created_evidence())
        evidence = parse_worker_result(
            payload,
            worker="feature-builder",
        )
        self.assertEqual(
            evidence["builder_manifest_digest"],
            manifest().manifest_digest,
        )
        parsed_receipt = BuilderProposalReceipt.from_payload(
            evidence["builder_proposal_receipt"]
        )
        self.assertEqual(
            parsed_receipt.receipt_digest,
            proposal_receipt().receipt_digest,
        )


    def test_created_evidence_receipt_is_manifest_bound(self) -> None:
        evidence = self.created_evidence()
        receipt = BuilderProposalReceipt.from_payload(
            evidence["builder_proposal_receipt"]
        )
        validate_builder_proposal_receipt(
            receipt,
            manifest(),
            evidence=evidence,
        )

    def test_created_evidence_rejects_receipt_digest_tamper(self) -> None:
        evidence = self.created_evidence()
        evidence["builder_proposal_receipt"]["receipt_digest"] = (
            "0" * 64
        )
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                evidence,
                manifest(),
            )

    def test_created_evidence_rejects_receipt_path_tamper(self) -> None:
        evidence = self.created_evidence()
        evidence["builder_proposal_receipt"]["paths"] = [
            "../escape.py"
        ]
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                evidence,
                manifest(),
            )

    def test_runtime_parser_requires_feature_receipt(self) -> None:
        evidence = self.created_evidence()
        evidence.pop("builder_proposal_receipt")
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(evidence),
                worker="feature-builder",
            )

    def test_runtime_parser_rejects_receipt_on_non_builder(self) -> None:
        evidence = {
            "status": "pull-request-created",
            "bot": "root-cause",
            "branch": "bot/specialist-root-cause-aaaaaaaaaaaaaaaa",
            "changed_lines": 1,
            "proposal_digest": "c" * 64,
            "base_sha": BASE,
            "supervisor_snapshot_fingerprint": SNAPSHOT,
            "execution_fingerprint": execution().fingerprint,
            "builder_proposal_receipt": proposal_receipt().as_dict(),
        }
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(evidence),
                worker="root-cause",
            )

    def test_exact_manifest_bound_evidence_is_accepted(self) -> None:
        validate_builder_worker_evidence(
            self.created_evidence(),
            manifest(),
        )

    def test_shared_custody_accepts_explicit_task_bound_branch(self) -> None:
        value = manifest()
        evidence = parse_worker_result(
            json.dumps(self.created_evidence()),
            worker="feature-builder",
        )
        validate_worker_evidence_custody(
            evidence,
            feature_custody(),
            expected_branch=builder_worker_branch(value),
        )

    def test_shared_custody_rejects_wrong_explicit_branch(self) -> None:
        evidence = parse_worker_result(
            json.dumps(self.created_evidence()),
            worker="feature-builder",
        )
        with self.assertRaises(SupervisorRuntimeError):
            validate_worker_evidence_custody(
                evidence,
                feature_custody(),
                expected_branch=(
                    "bot/specialist-feature-builder-" + ("f" * 16)
                ),
            )

    def test_existing_pr_parser_retains_task_identity(self) -> None:
        value = manifest()
        evidence = parse_worker_result(
            json.dumps(self.existing_evidence()),
            worker="feature-builder",
        )
        self.assertEqual(
            evidence["build_issue_number"],
            value.issue_number,
        )
        self.assertEqual(
            evidence["build_task_digest"],
            value.task_digest,
        )
        validate_worker_evidence_custody(
            evidence,
            feature_custody(),
            expected_branch=builder_worker_branch(value),
        )
        validate_builder_worker_evidence(evidence, value)

    def test_created_evidence_rejects_wrong_task_branch(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.created_evidence(
                    branch=(
                        "bot/specialist-feature-builder-" + ("f" * 16)
                    )
                ),
                manifest(),
            )

    def test_created_evidence_rejects_wrong_task_digest(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.created_evidence(task_digest="0" * 64),
                manifest(),
            )

    def test_created_evidence_rejects_wrong_issue_number(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.created_evidence(issue_number=999),
                manifest(),
            )

    def test_existing_pr_evidence_is_task_bound(self) -> None:
        validate_builder_worker_evidence(
            self.existing_evidence(),
            manifest(),
        )

    def test_existing_pr_rejects_cross_task_reuse(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.existing_evidence(task_digest="0" * 64),
                manifest(),
            )

    def test_manifest_evidence_digest_mismatch_is_rejected(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.created_evidence(digest="0" * 64),
                manifest(),
            )

    def test_non_builder_mutation_evidence_is_rejected(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                self.created_evidence(bot="root-cause"),
                manifest(),
            )

    def test_non_mutating_result_does_not_require_manifest_digest(self) -> None:
        validate_builder_worker_evidence(
            {
                "status": "no-change",
                "bot": "feature-builder",
            },
            manifest(),
        )

    def test_no_change_worker_output_is_admitted_without_custody_fields(self) -> None:
        evidence = parse_worker_result(
            json.dumps(
                {
                    "status": "no-change",
                    "bot": "feature-builder",
                    "summary": "authorized task already satisfied",
                }
            ),
            worker="feature-builder",
        )
        self.assertEqual(
            evidence,
            {
                "status": "no-change",
                "bot": "feature-builder",
            },
        )
        validate_worker_evidence_custody(
            evidence,
            feature_custody(),
        )
        validate_builder_worker_evidence(
            evidence,
            manifest(),
        )


if __name__ == "__main__":
    unittest.main()
