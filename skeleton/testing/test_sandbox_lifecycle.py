from __future__ import annotations

import hashlib
import unittest

from skeleton.shells.ai.sandbox_lifecycle import (
    ArtifactScanEvidence,
    SandboxLifecycleEvidence,
    SandboxLifecycleError,
    SecretProjectionEvidence,
    verify_sandbox_lifecycle,
)


NOW = 2_000_000_000.0


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence(**overrides) -> SandboxLifecycleEvidence:
    artifact = sha("artifact-a")
    values = {
        "execution_id": "exec-1",
        "backend_id": "sandbox-backend-v1",
        "isolation_mode": "container",
        "control_plane_pid": 100,
        "sandbox_pid": 200,
        "workdir_id": "workdir-1",
        "workdir_ephemeral": True,
        "cleanup_attempted": True,
        "cleanup_verified": True,
        "clean_environment": True,
        "ambient_credentials_present": False,
        "network_isolated": True,
        "child_process_policy": "deny",
        "started_at": NOW,
        "deadline_at": NOW + 60,
        "finished_at": NOW + 30,
        "output_bytes": 128,
        "max_output_bytes": 4096,
        "secret_projections": (
            SecretProjectionEvidence(
                secret_ref="secret-ref-1",
                scope="tool:repo-read",
                issued_at=NOW + 1,
                expires_at=NOW + 50,
                revoked_at_finish=True,
            ),
        ),
        "artifact_scans": (
            ArtifactScanEvidence(
                artifact_digest=artifact,
                scanner_id="scanner-v1",
                policy_digest=sha("scan-policy"),
                passed=True,
            ),
        ),
    }
    values.update(overrides)
    return SandboxLifecycleEvidence(**values)


class SandboxLifecycleTests(unittest.TestCase):
    def test_complete_lifecycle_evidence_is_accepted(self) -> None:
        item = evidence()
        report = verify_sandbox_lifecycle(
            item,
            required_artifact_digests=(sha("artifact-a"),),
            require_network_isolation=True,
        )
        self.assertTrue(report.accepted, report.reasons)
        self.assertEqual(report.evidence_digest, item.digest)

    def test_control_plane_process_cannot_execute_high_risk_work(self) -> None:
        item = evidence(sandbox_pid=100)
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn("execution-not-out-of-process", report.reasons)

    def test_cleanup_must_be_attempted_and_verified(self) -> None:
        item = evidence(cleanup_attempted=False, cleanup_verified=False)
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn("cleanup-not-attempted", report.reasons)
        self.assertIn("cleanup-not-verified", report.reasons)

    def test_ambient_credentials_and_dirty_environment_fail_closed(self) -> None:
        item = evidence(
            clean_environment=False,
            ambient_credentials_present=True,
        )
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn("environment-not-clean", report.reasons)
        self.assertIn("ambient-credentials-present", report.reasons)

    def test_network_isolation_is_required_when_policy_requests_it(self) -> None:
        item = evidence(network_isolated=False)
        denied = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(denied.accepted)
        self.assertIn("network-not-isolated", denied.reasons)

        allowed = verify_sandbox_lifecycle(
            item,
            require_network_isolation=False,
        )
        self.assertTrue(allowed.accepted, allowed.reasons)

    def test_output_budget_and_deadline_are_non_compensable(self) -> None:
        item = evidence(
            finished_at=NOW + 61,
            output_bytes=4097,
        )
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn("execution-deadline-exceeded", report.reasons)
        self.assertIn("output-budget-exceeded", report.reasons)

    def test_secret_projection_cannot_outlive_execution_deadline(self) -> None:
        item = evidence(
            secret_projections=(
                SecretProjectionEvidence(
                    secret_ref="secret-ref-1",
                    scope="tool:repo-read",
                    issued_at=NOW + 1,
                    expires_at=NOW + 61,
                    revoked_at_finish=True,
                ),
            )
        )
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn(
            "secret-projection-outlives-deadline:secret-ref-1",
            report.reasons,
        )

    def test_secret_projection_must_be_revoked_at_finish(self) -> None:
        item = evidence(
            secret_projections=(
                SecretProjectionEvidence(
                    secret_ref="secret-ref-1",
                    scope="tool:repo-read",
                    issued_at=NOW + 1,
                    expires_at=NOW + 50,
                    revoked_at_finish=False,
                ),
            )
        )
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn(
            "secret-projection-not-revoked:secret-ref-1",
            report.reasons,
        )

    def test_secret_projection_cannot_preexist_execution(self) -> None:
        item = evidence(
            secret_projections=(
                SecretProjectionEvidence(
                    secret_ref="secret-ref-1",
                    scope="tool:repo-read",
                    issued_at=NOW - 1,
                    expires_at=NOW + 50,
                    revoked_at_finish=True,
                ),
            )
        )
        report = verify_sandbox_lifecycle(
            item,
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        self.assertIn(
            "secret-projection-before-execution:secret-ref-1",
            report.reasons,
        )

    def test_required_artifact_must_have_passing_scan(self) -> None:
        missing = verify_sandbox_lifecycle(
            evidence(artifact_scans=()),
            required_artifact_digests=(sha("artifact-a"),),
            require_network_isolation=True,
        )
        self.assertFalse(missing.accepted)
        self.assertIn(
            f"artifact-scan-missing:{sha('artifact-a')}",
            missing.reasons,
        )

        failed = verify_sandbox_lifecycle(
            evidence(
                artifact_scans=(
                    ArtifactScanEvidence(
                        artifact_digest=sha("artifact-a"),
                        scanner_id="scanner-v1",
                        policy_digest=sha("scan-policy"),
                        passed=False,
                    ),
                )
            ),
            required_artifact_digests=(sha("artifact-a"),),
            require_network_isolation=True,
        )
        self.assertFalse(failed.accepted)
        self.assertIn(
            f"artifact-scan-failed:{sha('artifact-a')}",
            failed.reasons,
        )

    def test_duplicate_secret_or_artifact_identities_are_rejected(self) -> None:
        secret = SecretProjectionEvidence(
            secret_ref="secret-ref-1",
            scope="tool:repo-read",
            issued_at=NOW + 1,
            expires_at=NOW + 50,
            revoked_at_finish=True,
        )
        with self.assertRaisesRegex(SandboxLifecycleError, "secret projection refs"):
            evidence(secret_projections=(secret, secret))

        scan = ArtifactScanEvidence(
            artifact_digest=sha("artifact-a"),
            scanner_id="scanner-v1",
            policy_digest=sha("scan-policy"),
            passed=True,
        )
        with self.assertRaisesRegex(SandboxLifecycleError, "artifact scan digests"):
            evidence(artifact_scans=(scan, scan))

    def test_rejected_report_cannot_be_promoted(self) -> None:
        report = verify_sandbox_lifecycle(
            evidence(cleanup_verified=False),
            require_network_isolation=True,
        )
        self.assertFalse(report.accepted)
        with self.assertRaisesRegex(SandboxLifecycleError, "lifecycle rejected"):
            report.require_accepted()


if __name__ == "__main__":
    unittest.main()
