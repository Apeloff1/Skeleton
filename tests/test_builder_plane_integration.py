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
    builder_worker_branch,
    compile_builder_manifest,
    validate_builder_custody,
    validate_builder_worker_evidence,
)
from skeleton.automation.supervisor_runtime import (
    ExecutionIdentity,
    WorkerCustody,
    parse_worker_result,
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

    def test_exact_manifest_bound_evidence_is_accepted(self) -> None:
        validate_builder_worker_evidence(
            self.created_evidence(),
            manifest(),
        )

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


if __name__ == "__main__":
    unittest.main()
