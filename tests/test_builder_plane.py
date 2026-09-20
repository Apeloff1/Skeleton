from __future__ import annotations

import base64
import copy
import json
import unittest

from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.builder_plane import (
    MAX_BUDGET_CHANGED_LINES,
    MAX_BUDGET_FILES,
    MAX_BUDGET_TEST_DESCRIPTIONS,
    MAX_BUDGET_TOTAL_BYTES,
    BuilderBudget,
    BuilderManifest,
    BuilderPlaneError,
    BuilderProposalReceipt,
    BuilderStage,
    builder_worker_branch,
    compile_builder_manifest,
    compile_builder_proposal_receipt,
    manifest_prompt_fragment,
    validate_builder_custody,
    validate_builder_proposal_receipt,
)
from skeleton.automation.supervisor_runtime import ExecutionIdentity


REPO = "Apeloff1/Skeleton"
BASE = "a" * 40
SNAPSHOT = "b" * 64


def execution(
    *,
    repository: str = REPO,
    base_sha: str = BASE,
    run_id: str = "123",
) -> ExecutionIdentity:
    return ExecutionIdentity(
        repository=repository,
        base_sha=base_sha,
        default_branch="main",
        run_id=run_id,
        run_attempt="1",
    )


def issue(
    *,
    number: int = 41,
    title: str = "Add typed API builder support",
    body: str = (
        "Implement the API contract with focused tests and documentation. "
        "Keep integration behavior deterministic."
    ),
    labels: tuple[str, ...] = (
        "automation-approved",
        "enhancement",
        "api",
    ),
    updated_at: str = "2026-09-20T02:00:00Z",
) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": labels,
        "updatedAt": updated_at,
        "automation_authorized": True,
    }


def authorization(**overrides: object) -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        issue(**overrides),
    )


class BuilderCompilationTests(unittest.TestCase):
    def test_compile_is_deterministic(self) -> None:
        auth = authorization()
        first = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        second = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(first, second)
        self.assertEqual(first.manifest_digest, second.manifest_digest)

    def test_manifest_binds_all_custody_identities(self) -> None:
        auth = authorization()
        run = execution()
        manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=run,
        )
        self.assertEqual(manifest.repository, REPO)
        self.assertEqual(manifest.issue_number, auth.issue_number)
        self.assertEqual(manifest.issue_digest, auth.issue_digest)
        self.assertEqual(manifest.task_digest, auth.task_digest)
        self.assertEqual(manifest.snapshot_fingerprint, SNAPSHOT)
        self.assertEqual(
            manifest.execution_fingerprint,
            run.fingerprint,
        )
        self.assertEqual(manifest.base_sha, BASE)

    def test_manifest_has_single_mutation_stage(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        mutation = [
            stage
            for stage in manifest.stages
            if stage.mutation_allowed
        ]
        self.assertEqual(len(mutation), 1)
        self.assertEqual(mutation[0].stage_id, "implement")
        self.assertEqual(mutation[0].kind, "implement")

    def test_stage_graph_is_ordered_and_acyclic(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(
            [stage.stage_id for stage in manifest.stages],
            [
                "inspect",
                "design",
                "implement",
                "regression",
                "validate",
                "evidence",
            ],
        )
        seen: set[str] = set()
        for stage in manifest.stages:
            self.assertTrue(set(stage.depends_on) <= seen)
            seen.add(stage.stage_id)

    def test_signal_classification_is_canonical(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(
            manifest.signals,
            tuple(sorted(manifest.signals)),
        )
        self.assertIn("api-contract", manifest.signals)
        self.assertIn("documentation", manifest.signals)
        self.assertIn("integration", manifest.signals)
        self.assertIn("testing", manifest.signals)

    def test_unknown_feature_falls_back_to_general_signal(self) -> None:
        manifest = compile_builder_manifest(
            authorization(
                title="Add frobnicator",
                body="Implement frobnicator behavior.",
                labels=("automation-approved",),
            ),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertEqual(manifest.signals, ("general-feature",))

    def test_api_and_integration_work_receive_larger_file_budget(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertGreaterEqual(manifest.budget.max_files, 10)
        self.assertLessEqual(manifest.budget.max_files, MAX_BUDGET_FILES)

    def test_default_budget_never_exceeds_worker_hard_limits(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertLessEqual(
            manifest.budget.max_changed_lines,
            MAX_BUDGET_CHANGED_LINES,
        )
        self.assertLessEqual(
            manifest.budget.max_total_bytes,
            MAX_BUDGET_TOTAL_BYTES,
        )
        self.assertLessEqual(
            manifest.budget.max_test_descriptions,
            MAX_BUDGET_TEST_DESCRIPTIONS,
        )

    def test_acceptance_keeps_authority_boundary_explicit(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        rendered = " ".join(manifest.acceptance).lower()
        self.assertIn("authority", rendered)
        self.assertIn("workflow", rendered)
        self.assertIn("regression", rendered)
        self.assertIn("immutable", rendered)


class BuilderSerializationTests(unittest.TestCase):
    def manifest(self) -> BuilderManifest:
        return compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )

    def test_payload_round_trip(self) -> None:
        first = self.manifest()
        second = BuilderManifest.from_payload(first.as_dict())
        self.assertEqual(second, first)
        self.assertEqual(
            second.manifest_digest,
            first.manifest_digest,
        )

    def test_base64_round_trip(self) -> None:
        first = self.manifest()
        second = BuilderManifest.from_base64(first.to_base64())
        self.assertEqual(second, first)

    def test_payload_is_data_only(self) -> None:
        value = self.manifest().as_dict()
        forbidden = {
            "command",
            "executable",
            "module",
            "token",
            "permission",
            "workflow",
            "branch",
            "shell",
        }
        self.assertTrue(forbidden.isdisjoint(value))
        for stage in value["stages"]:
            self.assertTrue(forbidden.isdisjoint(stage))

    def test_extra_top_level_field_is_rejected(self) -> None:
        value = self.manifest().as_dict()
        value["command"] = "python anything.py"
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_payload(value)

    def test_missing_top_level_field_is_rejected(self) -> None:
        value = self.manifest().as_dict()
        del value["base_sha"]
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_payload(value)

    def test_manifest_digest_tamper_is_rejected(self) -> None:
        value = self.manifest().as_dict()
        value["manifest_digest"] = "0" * 64
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_payload(value)

    def test_nested_stage_tamper_is_rejected_by_digest(self) -> None:
        value = self.manifest().as_dict()
        value["stages"][0]["objective"] = "tampered"
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_payload(value)

    def test_nested_budget_tamper_is_rejected_by_digest(self) -> None:
        value = self.manifest().as_dict()
        value["budget"]["max_files"] -= 1
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_payload(value)

    def test_base64_rejects_trailing_non_base64_data(self) -> None:
        encoded = self.manifest().to_base64() + "!"
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_base64(encoded)

    def test_base64_rejects_non_json_payload(self) -> None:
        encoded = base64.b64encode(b"not-json").decode("ascii")
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest.from_base64(encoded)

    def test_input_payload_is_not_mutated(self) -> None:
        value = self.manifest().as_dict()
        before = copy.deepcopy(value)
        BuilderManifest.from_payload(value)
        self.assertEqual(value, before)


class BuilderBudgetTests(unittest.TestCase):
    def test_rejects_boolean_budget_values(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(max_files=True)

    def test_rejects_zero_file_budget(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(max_files=0)

    def test_rejects_file_budget_above_hard_cap(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(max_files=MAX_BUDGET_FILES + 1)

    def test_rejects_changed_line_budget_above_hard_cap(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(
                max_changed_lines=MAX_BUDGET_CHANGED_LINES + 1
            )

    def test_rejects_total_byte_budget_above_hard_cap(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(
                max_total_bytes=MAX_BUDGET_TOTAL_BYTES + 1
            )

    def test_rejects_test_description_budget_above_cap(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget(
                max_test_descriptions=(
                    MAX_BUDGET_TEST_DESCRIPTIONS + 1
                )
            )

    def test_budget_payload_requires_exact_shape(self) -> None:
        value = BuilderBudget().as_dict()
        value["shell"] = "bash"
        with self.assertRaises(BuilderPlaneError):
            BuilderBudget.from_payload(value)


class BuilderStageTests(unittest.TestCase):
    def stage(
        self,
        *,
        ordinal: int = 1,
        stage_id: str = "inspect",
        kind: str = "inspect",
        depends_on: tuple[str, ...] = (),
        mutation_allowed: bool = False,
    ) -> BuilderStage:
        return BuilderStage(
            ordinal=ordinal,
            stage_id=stage_id,
            kind=kind,
            objective="Inspect the relevant repository surface.",
            depends_on=depends_on,
            required_evidence=("Relevant source identified.",),
            mutation_allowed=mutation_allowed,
        )

    def test_rejects_invalid_stage_identifier(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            self.stage(stage_id="../escape")

    def test_rejects_duplicate_dependencies(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            self.stage(depends_on=("inspect", "inspect"))

    def test_rejects_non_boolean_mutation_flag(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            BuilderStage(
                ordinal=1,
                stage_id="inspect",
                kind="inspect",
                objective="Inspect",
                depends_on=(),
                required_evidence=("Evidence",),
                mutation_allowed=1,
            )

    def test_manifest_rejects_forward_dependency(self) -> None:
        inspect = self.stage(
            stage_id="inspect",
            depends_on=("later",),
        )
        implement = self.stage(
            ordinal=2,
            stage_id="implement",
            kind="implement",
            depends_on=("inspect",),
            mutation_allowed=True,
        )
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest(
                version=1,
                repository=REPO,
                issue_number=1,
                issue_digest="c" * 64,
                task_digest="d" * 64,
                snapshot_fingerprint=SNAPSHOT,
                execution_fingerprint="e" * 64,
                base_sha=BASE,
                budget=BuilderBudget(),
                stages=(inspect, implement),
                signals=("general-feature",),
                acceptance=("Accept.",),
            )

    def test_manifest_rejects_multiple_mutation_stages(self) -> None:
        first = self.stage(
            ordinal=1,
            stage_id="implement",
            kind="implement",
            mutation_allowed=True,
        )
        second = self.stage(
            ordinal=2,
            stage_id="implement-two",
            kind="implement",
            depends_on=("implement",),
            mutation_allowed=True,
        )
        with self.assertRaises(BuilderPlaneError):
            BuilderManifest(
                version=1,
                repository=REPO,
                issue_number=1,
                issue_digest="c" * 64,
                task_digest="d" * 64,
                snapshot_fingerprint=SNAPSHOT,
                execution_fingerprint="e" * 64,
                base_sha=BASE,
                budget=BuilderBudget(),
                stages=(first, second),
                signals=("general-feature",),
                acceptance=("Accept.",),
            )


class BuilderBranchIdentityTests(unittest.TestCase):
    def test_branch_is_stable_across_execution_and_snapshot_refresh(self) -> None:
        auth = authorization()
        first = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(run_id="123"),
        )
        second = compile_builder_manifest(
            auth,
            snapshot_fingerprint="c" * 64,
            execution=execution(run_id="999"),
        )
        self.assertEqual(
            builder_worker_branch(first),
            builder_worker_branch(second),
        )

    def test_branch_changes_when_authorized_task_changes(self) -> None:
        first = compile_builder_manifest(
            authorization(body="Implement capability A with tests."),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        second = compile_builder_manifest(
            authorization(body="Implement capability B with tests."),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        self.assertNotEqual(
            builder_worker_branch(first),
            builder_worker_branch(second),
        )

    def test_branch_changes_when_base_commit_changes(self) -> None:
        auth = authorization()
        first = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(base_sha="a" * 40),
        )
        second = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(base_sha="c" * 40),
        )
        self.assertNotEqual(
            builder_worker_branch(first),
            builder_worker_branch(second),
        )

    def test_branch_stays_inside_reserved_feature_builder_namespace(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        branch = builder_worker_branch(manifest)
        prefix = "bot/specialist-feature-builder-"
        self.assertTrue(branch.startswith(prefix))
        suffix = branch[len(prefix):]
        self.assertEqual(len(suffix), 16)
        self.assertTrue(
            all(char in "0123456789abcdef" for char in suffix)
        )


class BuilderCustodyTests(unittest.TestCase):
    def test_valid_custody_is_accepted(self) -> None:
        auth = authorization()
        run = execution()
        manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=run,
        )
        self.assertIs(
            validate_builder_custody(
                manifest,
                authorization=auth,
                snapshot_fingerprint=SNAPSHOT,
                execution=run,
            ),
            manifest,
        )

    def test_snapshot_mismatch_is_rejected(self) -> None:
        auth = authorization()
        manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with self.assertRaises(BuilderPlaneError):
            validate_builder_custody(
                manifest,
                authorization=auth,
                snapshot_fingerprint="f" * 64,
                execution=execution(),
            )

    def test_execution_mismatch_is_rejected(self) -> None:
        auth = authorization()
        manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with self.assertRaises(BuilderPlaneError):
            validate_builder_custody(
                manifest,
                authorization=auth,
                snapshot_fingerprint=SNAPSHOT,
                execution=execution(run_id="999"),
            )

    def test_authorization_mismatch_is_rejected(self) -> None:
        first = authorization()
        second = authorization(body="Implement a different task with tests.")
        manifest = compile_builder_manifest(
            first,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with self.assertRaises(BuilderPlaneError):
            validate_builder_custody(
                manifest,
                authorization=second,
                snapshot_fingerprint=SNAPSHOT,
                execution=execution(),
            )

    def test_cross_repository_compile_is_rejected(self) -> None:
        auth = authorization()
        with self.assertRaises(BuilderPlaneError):
            compile_builder_manifest(
                auth,
                snapshot_fingerprint=SNAPSHOT,
                execution=execution(
                    repository="Other/Skeleton"
                ),
            )

    def test_non_authorization_input_is_rejected(self) -> None:
        with self.assertRaises(BuilderPlaneError):
            compile_builder_manifest(
                object(),
                snapshot_fingerprint=SNAPSHOT,
                execution=execution(),
            )


class BuilderProposalReceiptTests(unittest.TestCase):
    def manifest(self) -> BuilderManifest:
        return compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )

    def receipt(self) -> BuilderProposalReceipt:
        value = self.manifest()
        return compile_builder_proposal_receipt(
            value,
            proposal_digest="c" * 64,
            branch=builder_worker_branch(value),
            files=(
                {
                    "path": "skeleton/feature.py",
                    "content": "VALUE = 1\n",
                },
                {
                    "path": "tests/test_feature.py",
                    "content": "def test_feature():\n    assert True\n",
                },
            ),
            tests=("focused feature regression",),
            changed_lines=7,
        )

    def test_receipt_is_deterministic_and_canonical(self) -> None:
        first = self.receipt()
        second = self.receipt()
        self.assertEqual(first, second)
        self.assertEqual(first.receipt_digest, second.receipt_digest)
        self.assertEqual(
            first.paths,
            (
                "skeleton/feature.py",
                "tests/test_feature.py",
            ),
        )

    def test_receipt_round_trip_preserves_digest(self) -> None:
        first = self.receipt()
        second = BuilderProposalReceipt.from_payload(
            first.as_dict()
        )
        self.assertEqual(second, first)
        self.assertEqual(
            second.receipt_digest,
            first.receipt_digest,
        )

    def test_receipt_digest_tamper_is_rejected(self) -> None:
        payload = self.receipt().as_dict()
        payload["receipt_digest"] = "0" * 64
        with self.assertRaises(BuilderPlaneError):
            BuilderProposalReceipt.from_payload(payload)

    def test_receipt_path_tamper_is_rejected(self) -> None:
        payload = self.receipt().as_dict()
        payload["paths"] = ["../escape.py"]
        with self.assertRaises(BuilderPlaneError):
            BuilderProposalReceipt.from_payload(payload)

    def test_receipt_requires_canonical_path_order(self) -> None:
        payload = self.receipt().as_dict()
        payload["paths"] = list(reversed(payload["paths"]))
        payload["receipt_digest"] = BuilderProposalReceipt(
            version=payload["version"],
            repository=payload["repository"],
            issue_number=payload["issue_number"],
            manifest_digest=payload["manifest_digest"],
            task_digest=payload["task_digest"],
            snapshot_fingerprint=payload["snapshot_fingerprint"],
            execution_fingerprint=payload["execution_fingerprint"],
            base_sha=payload["base_sha"],
            branch=payload["branch"],
            proposal_digest=payload["proposal_digest"],
            paths=tuple(sorted(payload["paths"])),
            changed_lines=payload["changed_lines"],
            total_bytes=payload["total_bytes"],
            test_count=payload["test_count"],
            tests_digest=payload["tests_digest"],
        ).receipt_digest
        with self.assertRaises(BuilderPlaneError):
            BuilderProposalReceipt.from_payload(payload)

    def test_compile_rejects_wrong_task_branch(self) -> None:
        value = self.manifest()
        with self.assertRaises(BuilderPlaneError):
            compile_builder_proposal_receipt(
                value,
                proposal_digest="c" * 64,
                branch=(
                    "bot/specialist-feature-builder-"
                    + ("f" * 16)
                ),
                files=(
                    {
                        "path": "skeleton/feature.py",
                        "content": "VALUE = 1\n",
                    },
                ),
                tests=("focused regression",),
                changed_lines=1,
            )

    def test_compile_rejects_manifest_file_budget_overflow(self) -> None:
        value = self.manifest()
        files = tuple(
            {
                "path": f"skeleton/generated_{index}.py",
                "content": "VALUE = 1\n",
            }
            for index in range(value.budget.max_files + 1)
        )
        with self.assertRaises(BuilderPlaneError):
            compile_builder_proposal_receipt(
                value,
                proposal_digest="c" * 64,
                branch=builder_worker_branch(value),
                files=files,
                tests=(),
                changed_lines=1,
            )

    def test_validate_receipt_binds_manifest(self) -> None:
        value = self.manifest()
        receipt = self.receipt()
        validate_builder_proposal_receipt(
            receipt,
            value,
        )

        different = compile_builder_manifest(
            authorization(body="Implement another tested API task."),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        with self.assertRaises(BuilderPlaneError):
            validate_builder_proposal_receipt(
                receipt,
                different,
            )


class BuilderPromptTests(unittest.TestCase):
    def test_prompt_fragment_is_canonical_json(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        rendered = manifest_prompt_fragment(manifest)
        payload = json.loads(rendered)
        self.assertEqual(
            payload["manifest_digest"],
            manifest.manifest_digest,
        )
        self.assertEqual(
            payload["budget"],
            manifest.budget.as_dict(),
        )

    def test_prompt_fragment_does_not_duplicate_issue_body(self) -> None:
        secret_phrase = "UNIQUE-ISSUE-BODY-CONTENT"
        auth = authorization(
            body=secret_phrase + " implement a tested feature"
        )
        manifest = compile_builder_manifest(
            auth,
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        rendered = manifest_prompt_fragment(manifest)
        self.assertNotIn(secret_phrase, rendered)

    def test_prompt_fragment_contains_no_execution_primitive_fields(self) -> None:
        manifest = compile_builder_manifest(
            authorization(),
            snapshot_fingerprint=SNAPSHOT,
            execution=execution(),
        )
        payload = json.loads(manifest_prompt_fragment(manifest))
        rendered_keys = set(payload)
        self.assertTrue(
            {
                "command",
                "executable",
                "module",
                "token",
                "permission",
                "workflow",
                "shell",
                "branch",
            }.isdisjoint(rendered_keys)
        )


if __name__ == "__main__":
    unittest.main()
