"""Governed deployment gateway for Skeleton's atomic release backend.

Preparation compiles a deterministic plan, samples a stable control-plane preflight,
and issues a short-lived authorization bound to both plan and whole-system root.
Execution re-evaluates safety immediately before the side effect, consumes the
authorization exactly once, activates the release atomically, then records a
post-activation transition receipt binding the observed pre/post system roots.

Authorization and completed-transition evidence is automatically anchored into the
append-only deployment checkpoint ledger. The checkpoint ledger is deliberately
excluded from the system root it summarizes, avoiding self-reference while giving
external verifiers a durable publication history. A genesis checkpoint is published
on construction so a healthy empty deployment state is externally pinnable too.

Transition receipts are deliberately excluded from the system root they attest to.
If a process dies after release activation but before receipt persistence, the gap is
not silently reconstructed from later state: status exposes a hard evidence gap and
replay fails closed until an explicit forensic reconciliation path handles it.

Trust decisions in this module never rely on Python's implicit coercion rules. IDs,
roots, retry counts, and persisted evidence must already have their canonical JSON
types and representations before they cross the gateway boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
from pathlib import Path
import re
from typing import Any, Mapping

from core.atomic_release_deployer import AtomicReleaseDeployer, ReleaseRecord
from core.control_plane_deployment import (
    ControlPlaneDeploymentPreflight,
    evaluate_control_plane_deployment,
    verify_control_plane_deployment_preflight,
)
from core.deployment_authorization import (
    DeploymentAuthorization,
    DeploymentAuthorizationError,
    DeploymentAuthorizationLedger,
    DeploymentConsumption,
    plan_digest,
)
from core.deployment_checkpoint_ledger import (
    DeploymentCheckpointLedger,
    DeploymentCheckpointLedgerError,
    DeploymentCheckpointPublication,
)
from core.deployment_evidence_checkpoint import (
    DeploymentEvidenceCheckpoint,
    build_deployment_evidence_checkpoint,
)
from core.deployment_planner import compile_deployment_plan, verify_deployment_plan
from core.deployment_receipts import DeploymentReceiptLedger, DeploymentTransitionReceipt

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DeploymentGatewayError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedDeployment:
    plan: dict[str, Any]
    preflight: ControlPlaneDeploymentPreflight
    authorization: DeploymentAuthorization


@dataclass(frozen=True, slots=True)
class DeploymentExecution:
    authorization_id: str
    resumed: bool
    preflight: ControlPlaneDeploymentPreflight | None
    consumption: DeploymentConsumption
    release: ReleaseRecord
    transition_receipt: DeploymentTransitionReceipt


def _canonical_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a canonical non-empty string")
    return value


def _canonical_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase sha256")
    return value


def _bounded_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise ValueError(f"{field} must be an integer between {minimum} and {maximum}")
    return value


class DeploymentGateway:
    def __init__(self, root: str | Path, *, control_plane) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.control_plane = control_plane
        self.authorizations = DeploymentAuthorizationLedger(self.root / "authorizations")
        self.releases = AtomicReleaseDeployer(self.root / "releases")
        self.receipts = DeploymentReceiptLedger(self.root / "transition-receipts")
        self.checkpoints = DeploymentCheckpointLedger(self.root / "evidence-checkpoints")
        self.publish_evidence_checkpoint()

    @staticmethod
    def _plan(value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("deployment input must be an object")
        if "plan_sha256" in value or "schema_version" in value:
            if not verify_deployment_plan(value):
                raise ValueError("compiled deployment plan failed semantic verification")
            return dict(value)
        return compile_deployment_plan(value)

    def _system_root_sha256(self) -> str:
        raw = self.control_plane.system_root()
        if not isinstance(raw, Mapping):
            raise DeploymentGatewayError("control-plane system root must be an object")
        try:
            return _canonical_sha256(raw.get("root_sha256"), "control-plane system root")
        except ValueError as exc:
            raise DeploymentGatewayError(str(exc)) from exc

    def evidence_checkpoint(self) -> DeploymentEvidenceCheckpoint:
        return build_deployment_evidence_checkpoint(self)

    def publish_evidence_checkpoint(self) -> DeploymentCheckpointPublication:
        """Publish current verified evidence, retrying only to converge concurrent writers."""
        last_error: DeploymentCheckpointLedgerError | None = None
        for _ in range(3):
            checkpoint = self.evidence_checkpoint()
            try:
                return self.checkpoints.publish(checkpoint)
            except DeploymentCheckpointLedgerError as exc:
                last_error = exc
                # Another process may have advanced the underlying ledgers between our
                # snapshot and checkpoint publication. Rebuild from current verified
                # state; persistent ledger corruption or real regression will fail again.
                continue
        raise DeploymentGatewayError(f"deployment checkpoint publication failed: {last_error}") from last_error

    def prepare(self, deployment_input: dict[str, Any], *, ttl_seconds: int = 300,
                max_attempts: int = 3) -> PreparedDeployment:
        _bounded_int(ttl_seconds, "authorization ttl", minimum=1, maximum=3600)
        _bounded_int(max_attempts, "max_attempts", minimum=1, maximum=10)
        plan = self._plan(deployment_input)
        preflight = evaluate_control_plane_deployment(self.control_plane, max_attempts=max_attempts)
        if not verify_control_plane_deployment_preflight(preflight):
            raise DeploymentGatewayError("deployment preflight attestation failed verification")
        if not preflight.allowed or not preflight.stable:
            raise DeploymentGatewayError("deployment preflight blocked authorization")
        authorization = self.authorizations.issue(preflight=preflight, plan=plan, ttl_seconds=ttl_seconds)
        self.publish_evidence_checkpoint()
        return PreparedDeployment(plan, preflight, authorization)

    def _fresh_preflight(self, *, expected_root: str, max_attempts: int) -> ControlPlaneDeploymentPreflight:
        expected_root = _canonical_sha256(expected_root, "expected system root")
        _bounded_int(max_attempts, "max_attempts", minimum=1, maximum=10)
        preflight = evaluate_control_plane_deployment(self.control_plane, max_attempts=max_attempts)
        if not verify_control_plane_deployment_preflight(preflight):
            raise DeploymentGatewayError("fresh deployment preflight attestation failed verification")
        if not preflight.allowed or not preflight.stable:
            raise DeploymentGatewayError("fresh deployment preflight no longer authorizes deployment")
        if not hmac.compare_digest(preflight.root_after_sha256, expected_root):
            raise DeploymentGatewayError("whole-system root changed since deployment authorization")
        return preflight

    def _record_transition(self, *, release: ReleaseRecord, consumption: DeploymentConsumption,
                           pre_system_root_sha256: str) -> DeploymentTransitionReceipt:
        pre_system_root_sha256 = _canonical_sha256(pre_system_root_sha256, "pre-system root")
        post_root = self._system_root_sha256()
        if hmac.compare_digest(pre_system_root_sha256, post_root):
            raise DeploymentGatewayError("release activation did not rotate the whole-system root")
        return self.receipts.record(
            authorization_id=consumption.authorization_id,
            plan_sha256=consumption.plan_sha256,
            release_id=release.release_id,
            release_sha256=release.sha256,
            target=release.target,
            environment=release.environment,
            artifact=release.artifact,
            pre_system_root_sha256=pre_system_root_sha256,
            post_system_root_sha256=post_root,
            executed_at=release.activated_at,
        )

    def execute(self, authorization_id: str, deployment_input: dict[str, Any], *,
                max_attempts: int = 3) -> DeploymentExecution:
        authorization_id = _canonical_text(authorization_id, "authorization_id")
        _bounded_int(max_attempts, "max_attempts", minimum=1, maximum=10)
        plan = self._plan(deployment_input)
        expected_plan = plan_digest(plan)

        existing_release = self.releases.find_by_authorization(authorization_id)
        existing_consumption = self.authorizations.consumption(authorization_id)
        existing_receipt = self.receipts.by_authorization(authorization_id)
        authorization = self.authorizations.authorization(authorization_id)
        if authorization is None:
            raise DeploymentGatewayError("deployment authorization not found")
        if not hmac.compare_digest(authorization.plan_sha256, expected_plan):
            raise DeploymentGatewayError("deployment input does not match authorized plan")

        if existing_release is not None:
            if existing_consumption is None:
                raise DeploymentGatewayError("release exists without authorization consumption evidence")
            if existing_receipt is None:
                raise DeploymentGatewayError("deployment transition evidence gap: activated release has no transition receipt")
            if (existing_release.plan_sha256 != existing_consumption.plan_sha256
                    or existing_release.system_root_sha256 != existing_consumption.system_root_sha256
                    or existing_receipt.release_sha256 != existing_release.sha256
                    or existing_receipt.plan_sha256 != existing_consumption.plan_sha256
                    or existing_receipt.pre_system_root_sha256 != existing_consumption.system_root_sha256):
                raise DeploymentGatewayError("release/authorization/transition evidence mismatch")
            self.publish_evidence_checkpoint()
            return DeploymentExecution(authorization_id, True, None, existing_consumption,
                                       existing_release, existing_receipt)

        if existing_receipt is not None:
            raise DeploymentGatewayError("transition receipt exists without activated release")

        if existing_consumption is not None:
            preflight = self._fresh_preflight(
                expected_root=existing_consumption.system_root_sha256,
                max_attempts=max_attempts,
            )
            if not hmac.compare_digest(existing_consumption.plan_sha256, expected_plan):
                raise DeploymentGatewayError("consumed authorization is bound to a different deployment plan")
            release = self.releases.activate(plan, existing_consumption)
            receipt = self._record_transition(
                release=release,
                consumption=existing_consumption,
                pre_system_root_sha256=existing_consumption.system_root_sha256,
            )
            self.publish_evidence_checkpoint()
            return DeploymentExecution(authorization_id, True, preflight, existing_consumption,
                                       release, receipt)

        preflight = self._fresh_preflight(
            expected_root=authorization.system_root_sha256,
            max_attempts=max_attempts,
        )
        try:
            consumption = self.authorizations.consume(
                authorization_id,
                current_system_root_sha256=preflight.root_after_sha256,
                plan=plan,
            )
        except DeploymentAuthorizationError as exc:
            raise DeploymentGatewayError(str(exc)) from exc
        release = self.releases.activate(plan, consumption)
        receipt = self._record_transition(
            release=release,
            consumption=consumption,
            pre_system_root_sha256=preflight.root_after_sha256,
        )
        self.publish_evidence_checkpoint()
        return DeploymentExecution(authorization_id, False, preflight, consumption, release, receipt)

    def evidence_gaps(self) -> list[dict[str, str]]:
        releases = {row.authorization_id: row for row in self.releases.snapshot()}
        receipts = {row.authorization_id: row for row in self.receipts.snapshot()}
        authorization_events = self.authorizations.snapshot_events()
        consumes: dict[str, dict[str, Any]] = {}
        for row in authorization_events:
            if row.get("kind") != "consume":
                continue
            authorization_id = row.get("authorization_id")
            if not isinstance(authorization_id, str) or not authorization_id:
                raise DeploymentGatewayError("verified authorization event has malformed identity")
            consumes[authorization_id] = row

        gaps: list[dict[str, str]] = []
        for authorization_id, consume in consumes.items():
            release = releases.get(authorization_id)
            if release is None:
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": "",
                    "kind": "consumption_without_release",
                })
                continue
            plan_sha = consume.get("plan_sha256")
            system_root = consume.get("system_root_sha256")
            if not isinstance(plan_sha, str) or not isinstance(system_root, str):
                raise DeploymentGatewayError("verified authorization consumption has malformed evidence types")
            if release.plan_sha256 != plan_sha or release.system_root_sha256 != system_root:
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": release.release_id,
                    "kind": "release_consumption_mismatch",
                })

        for authorization_id, release in releases.items():
            if authorization_id not in consumes:
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": release.release_id,
                    "kind": "release_without_consumption",
                })
            receipt = receipts.get(authorization_id)
            if receipt is None:
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": release.release_id,
                    "kind": "release_without_transition_receipt",
                })
                continue
            if (receipt.release_sha256 != release.sha256
                    or receipt.plan_sha256 != release.plan_sha256
                    or receipt.pre_system_root_sha256 != release.system_root_sha256
                    or receipt.target != release.target
                    or receipt.environment != release.environment
                    or receipt.artifact != release.artifact):
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": release.release_id,
                    "kind": "release_receipt_mismatch",
                })

        for authorization_id, receipt in receipts.items():
            if authorization_id not in releases:
                gaps.append({
                    "authorization_id": authorization_id,
                    "release_id": receipt.release_id,
                    "kind": "transition_receipt_without_release",
                })

        return sorted(gaps, key=lambda row: (row["authorization_id"], row["kind"], row["release_id"]))

    def portability_status(self) -> dict[str, Any]:
        """Classify completed releases by independent proof reconstructability.

        Old ledgers may contain only preflight/plan digests. Those records remain
        hash-chain verified, but an external verifier cannot reconstruct the exact
        authorized decision and rollout body from repository-independent evidence.
        """
        from core.deployment_proof import DEPLOYMENT_PROOF_VERSION

        issues: dict[str, dict[str, Any]] = {}
        for row in self.authorizations.snapshot_events():
            if row.get("kind") != "issue":
                continue
            authorization_id = row.get("authorization_id")
            if not isinstance(authorization_id, str) or not authorization_id:
                raise DeploymentGatewayError("verified authorization issue has malformed identity")
            issues[authorization_id] = row
        releases = self.releases.snapshot()
        receipts = {row.authorization_id: row for row in self.receipts.snapshot()}
        fully_portable = 0
        legacy_preflight_hash_only = 0
        legacy_plan_hash_only = 0
        incomplete_transition_evidence = 0

        for release in releases:
            issue = issues.get(release.authorization_id)
            receipt = receipts.get(release.authorization_id)
            if issue is None or receipt is None:
                incomplete_transition_evidence += 1
                continue
            has_preflight = isinstance(issue.get("preflight"), dict)
            has_plan = isinstance(issue.get("plan"), dict)
            if has_preflight and has_plan:
                fully_portable += 1
            else:
                if not has_preflight:
                    legacy_preflight_hash_only += 1
                if not has_plan:
                    legacy_plan_hash_only += 1

        completed = len(releases)
        legacy_or_incomplete = completed - fully_portable
        return {
            "proof_version": DEPLOYMENT_PROOF_VERSION,
            "completed_releases": completed,
            "fully_portable": fully_portable,
            "legacy_or_incomplete": legacy_or_incomplete,
            "legacy_preflight_hash_only": legacy_preflight_hash_only,
            "legacy_plan_hash_only": legacy_plan_hash_only,
            "incomplete_transition_evidence": incomplete_transition_evidence,
            "all_completed_releases_portable": completed == fully_portable,
        }

    def portable_proof(self, authorization_id: str):
        from core.deployment_proof import build_portable_deployment_proof
        authorization_id = _canonical_text(authorization_id, "authorization_id")
        return build_portable_deployment_proof(self, authorization_id)

    def status(self) -> dict[str, Any]:
        gaps = self.evidence_gaps()
        portability = self.portability_status()
        current_checkpoint = self.evidence_checkpoint()
        latest_publication = self.checkpoints.latest()
        checkpoint_current = (
            latest_publication is not None
            and hmac.compare_digest(latest_publication.checkpoint_root_sha256, current_checkpoint.root_sha256)
        )
        internally_verified = len(gaps) == 0
        independently_verifiable = internally_verified and portability["all_completed_releases_portable"]
        return {
            "authorization": self.authorizations.status(),
            "release_backend": self.releases.status(),
            "transition_receipts": self.receipts.status(),
            "evidence_gaps": gaps,
            "evidence_gap_count": len(gaps),
            "portability": portability,
            "evidence_checkpoint": asdict(current_checkpoint),
            "checkpoint_publication": self.checkpoints.status(),
            "checkpoint_current": checkpoint_current,
            "verified": internally_verified,
            "independently_verifiable": independently_verifiable,
            "externally_pinnable": independently_verifiable and checkpoint_current,
        }

    def root_component(self) -> dict[str, Any]:
        """Product-state projection safe to include in the system root.

        Outstanding permissions, transition receipts, and checkpoint publications are
        intentionally excluded: issuing permission must not mutate the root it
authorizes; a receipt cannot be part of the root it attests; and a checkpoint cannot
        become part of the state it summarizes. Activated release state remains
        consequential product state and therefore rotates the root in the canonical
        ProductControlPlane, where this component is included in system_root().
        """
        return {"release_backend": self.releases.status()}

    @staticmethod
    def prepared_dict(prepared: PreparedDeployment) -> dict[str, Any]:
        return {"plan": prepared.plan, "preflight": asdict(prepared.preflight),
                "authorization": asdict(prepared.authorization)}

    @staticmethod
    def execution_dict(execution: DeploymentExecution) -> dict[str, Any]:
        return {
            "authorization_id": execution.authorization_id,
            "resumed": execution.resumed,
            "preflight": asdict(execution.preflight) if execution.preflight is not None else None,
            "consumption": asdict(execution.consumption),
            "release": asdict(execution.release),
            "transition_receipt": asdict(execution.transition_receipt),
        }
