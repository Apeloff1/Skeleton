from __future__ import annotations

import hashlib
import json
import unittest

from skeleton.automation.build_authority import BuildAuthorization
from skeleton.automation.builder_plane import (
    BuilderManifest,
    BuilderPlaneError,
    BuilderRepairReceipt,
    builder_worker_branch,
    compile_builder_manifest,
    compile_builder_repair_receipt,
    validate_builder_repair_receipt,
    validate_builder_worker_evidence,
)
from skeleton.automation.supervisor_runtime import (
    ExecutionIdentity,
    SupervisorRuntimeError,
    canonical_json,
    parse_worker_result,
)


REPO = "Apeloff1/Skeleton"
BASE = "a" * 40
PARENT = "d" * 40
SNAPSHOT = "b" * 64


def execution() -> ExecutionIdentity:
    return ExecutionIdentity(
        repository=REPO,
        base_sha=BASE,
        default_branch="main",
        run_id="4242",
        run_attempt="1",
    )


def authorization() -> BuildAuthorization:
    return BuildAuthorization.from_issue(
        REPO,
        {
            "number": 177,
            "title": "Repair typed builder lifecycle",
            "body": (
                "Implement the approved feature and regression coverage "
                "while repairing failed CI deterministically."
            ),
            "labels": (
                "automation-approved",
                "enhancement",
                "integration",
            ),
            "updatedAt": "2026-09-20T09:30:00Z",
            "automation_authorized": True,
        },
    )


def manifest() -> BuilderManifest:
    return compile_builder_manifest(
        authorization(),
        snapshot_fingerprint=SNAPSHOT,
        execution=execution(),
    )


def repair_evidence(
    *,
    paths: tuple[str, ...] = ("skeleton/feature.py",),
) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "followup_fingerprint": "e" * 64,
        "architecture_fingerprint": "f" * 64,
        "before_fingerprint": "1" * 64,
        "after_fingerprint": "2" * 64,
        "validation_fingerprint": "3" * 64,
        "review_verdict": "accept",
        "review_rounds": 1,
        "model_calls": 2,
        "changed_paths": list(paths),
    }
    return {
        **unsigned,
        "fingerprint": hashlib.sha256(
            canonical_json(unsigned)
        ).hexdigest(),
    }


def receipt() -> BuilderRepairReceipt:
    value = manifest()
    return compile_builder_repair_receipt(
        value,
        pull_request=91,
        parent_sha=PARENT,
        proposal_digest="c" * 64,
        branch=builder_worker_branch(value),
        files=(
            {
                "path": "skeleton/feature.py",
                "content": "VALUE = 2\n",
            },
        ),
        tests=("CI regression passes",),
        changed_lines=2,
        repair_evidence=repair_evidence(),
    )


def updated_evidence() -> dict[str, object]:
    value = manifest()
    repair = receipt()
    return {
        "status": "pull-request-updated",
        "bot": "feature-builder",
        "branch": builder_worker_branch(value),
        "pull_request": 91,
        "changed_lines": 2,
        "proposal_digest": "c" * 64,
        "base_sha": BASE,
        "supervisor_snapshot_fingerprint": SNAPSHOT,
        "execution_fingerprint": execution().fingerprint,
        "build_issue_number": value.issue_number,
        "build_task_digest": value.task_digest,
        "builder_manifest_digest": value.manifest_digest,
        "repair_parent_sha": PARENT,
        "builder_repair_receipt": repair.as_dict(),
    }


class BuilderRepairReceiptTests(unittest.TestCase):
    def test_receipt_is_deterministic(self) -> None:
        first = receipt()
        second = receipt()
        self.assertEqual(first, second)
        self.assertEqual(
            first.receipt_digest,
            second.receipt_digest,
        )

    def test_receipt_round_trip(self) -> None:
        first = receipt()
        second = BuilderRepairReceipt.from_payload(
            first.as_dict()
        )
        self.assertEqual(second, first)

    def test_receipt_digest_tamper_is_rejected(self) -> None:
        payload = receipt().as_dict()
        payload["receipt_digest"] = "0" * 64
        with self.assertRaises(BuilderPlaneError):
            BuilderRepairReceipt.from_payload(payload)

    def test_compile_rejects_repair_evidence_fingerprint_tamper(
        self,
    ) -> None:
        value = manifest()
        evidence = repair_evidence()
        evidence["fingerprint"] = "0" * 64
        with self.assertRaises(BuilderPlaneError):
            compile_builder_repair_receipt(
                value,
                pull_request=91,
                parent_sha=PARENT,
                proposal_digest="c" * 64,
                branch=builder_worker_branch(value),
                files=(
                    {
                        "path": "skeleton/feature.py",
                        "content": "VALUE = 2\n",
                    },
                ),
                tests=("CI regression passes",),
                changed_lines=2,
                repair_evidence=evidence,
            )

    def test_compile_rejects_repair_path_mismatch(self) -> None:
        value = manifest()
        with self.assertRaises(BuilderPlaneError):
            compile_builder_repair_receipt(
                value,
                pull_request=91,
                parent_sha=PARENT,
                proposal_digest="c" * 64,
                branch=builder_worker_branch(value),
                files=(
                    {
                        "path": "skeleton/feature.py",
                        "content": "VALUE = 2\n",
                    },
                ),
                tests=("CI regression passes",),
                changed_lines=2,
                repair_evidence=repair_evidence(
                    paths=("tests/test_feature.py",)
                ),
            )

    def test_compile_rejects_base_as_repair_parent(self) -> None:
        value = manifest()
        with self.assertRaises(BuilderPlaneError):
            compile_builder_repair_receipt(
                value,
                pull_request=91,
                parent_sha=BASE,
                proposal_digest="c" * 64,
                branch=builder_worker_branch(value),
                files=(
                    {
                        "path": "skeleton/feature.py",
                        "content": "VALUE = 2\n",
                    },
                ),
                tests=("CI regression passes",),
                changed_lines=2,
                repair_evidence=repair_evidence(),
            )

    def test_validate_binds_exact_worker_evidence(self) -> None:
        validate_builder_repair_receipt(
            receipt(),
            manifest(),
            evidence=updated_evidence(),
        )

    def test_validate_rejects_different_parent(self) -> None:
        evidence = updated_evidence()
        evidence["repair_parent_sha"] = "9" * 40
        with self.assertRaises(BuilderPlaneError):
            validate_builder_repair_receipt(
                receipt(),
                manifest(),
                evidence=evidence,
            )


class BuilderRepairWorkerEvidenceTests(unittest.TestCase):
    def test_exact_updated_evidence_is_accepted(self) -> None:
        validate_builder_worker_evidence(
            updated_evidence(),
            manifest(),
        )

    def test_updated_evidence_without_receipt_is_rejected(self) -> None:
        evidence = updated_evidence()
        evidence.pop("builder_repair_receipt")
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                evidence,
                manifest(),
            )

    def test_updated_evidence_with_tampered_receipt_is_rejected(
        self,
    ) -> None:
        evidence = updated_evidence()
        evidence["builder_repair_receipt"]["parent_sha"] = "9" * 40
        with self.assertRaises(BuilderPlaneError):
            validate_builder_worker_evidence(
                evidence,
                manifest(),
            )

    def test_runtime_parser_retains_repair_receipt(self) -> None:
        parsed = parse_worker_result(
            json.dumps(updated_evidence()),
            worker="feature-builder",
        )
        self.assertEqual(
            parsed["builder_repair_receipt"]["receipt_digest"],
            receipt().receipt_digest,
        )

    def test_runtime_parser_requires_repair_receipt(self) -> None:
        evidence = updated_evidence()
        evidence.pop("builder_repair_receipt")
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(evidence),
                worker="feature-builder",
            )

    def test_runtime_parser_rejects_repair_receipt_on_other_worker(
        self,
    ) -> None:
        evidence = {
            "status": "pull-request-updated",
            "bot": "root-cause",
            "branch": "bot/specialist-root-cause-aaaaaaaaaaaaaaaa",
            "pull_request": 91,
            "changed_lines": 2,
            "proposal_digest": "c" * 64,
            "base_sha": BASE,
            "supervisor_snapshot_fingerprint": SNAPSHOT,
            "execution_fingerprint": execution().fingerprint,
            "repair_parent_sha": PARENT,
            "builder_repair_receipt": receipt().as_dict(),
        }
        with self.assertRaises(SupervisorRuntimeError):
            parse_worker_result(
                json.dumps(evidence),
                worker="root-cause",
            )


if __name__ == "__main__":
    unittest.main()
