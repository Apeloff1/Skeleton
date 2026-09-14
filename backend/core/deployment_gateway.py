"""Governed deployment gateway for Skeleton's atomic release backend.

Preparation compiles the deployment plan, samples a stable control-plane preflight,
and issues a short-lived authorization bound to both plan and whole-system root.
Execution re-evaluates deployment safety immediately before the side effect, consumes
the authorization exactly once, then activates the release atomically.

A completed activation is itself the durable product-state proof. Replaying an
already-completed authorization returns that proof without demanding the *old*
pre-deploy system root still be current; a consumed-but-not-activated authorization,
by contrast, may resume only while its original root is still current and a fresh
preflight remains authorizing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
from pathlib import Path
from typing import Any

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
from core.deployment_planner import compile_deployment_plan, verify_deployment_plan


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


class DeploymentGateway:
    def __init__(self, root: str | Path, *, control_plane) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.control_plane = control_plane
        self.authorizations = DeploymentAuthorizationLedger(self.root / "authorizations")
        self.releases = AtomicReleaseDeployer(self.root / "releases")

    @staticmethod
    def _plan(value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("deployment input must be an object")
        if verify_deployment_plan(value):
            return dict(value)
        return compile_deployment_plan(value)

    def prepare(self, deployment_input: dict[str, Any], *, ttl_seconds: int = 300,
                max_attempts: int = 3) -> PreparedDeployment:
        plan = self._plan(deployment_input)
        preflight = evaluate_control_plane_deployment(self.control_plane, max_attempts=max_attempts)
        if not verify_control_plane_deployment_preflight(preflight):
            raise DeploymentGatewayError("deployment preflight attestation failed verification")
        if not preflight.allowed or not preflight.stable:
            raise DeploymentGatewayError("deployment preflight blocked authorization")
        authorization = self.authorizations.issue(preflight=preflight, plan=plan, ttl_seconds=ttl_seconds)
        return PreparedDeployment(plan, preflight, authorization)

    def _fresh_preflight(self, *, expected_root: str, max_attempts: int) -> ControlPlaneDeploymentPreflight:
        preflight = evaluate_control_plane_deployment(self.control_plane, max_attempts=max_attempts)
        if not verify_control_plane_deployment_preflight(preflight):
            raise DeploymentGatewayError("fresh deployment preflight attestation failed verification")
        if not preflight.allowed or not preflight.stable:
            raise DeploymentGatewayError("fresh deployment preflight no longer authorizes deployment")
        if not hmac.compare_digest(preflight.root_after_sha256, expected_root):
            raise DeploymentGatewayError("whole-system root changed since deployment authorization")
        return preflight

    def execute(self, authorization_id: str, deployment_input: dict[str, Any], *,
                max_attempts: int = 3) -> DeploymentExecution:
        authorization_id = str(authorization_id).strip()
        if not authorization_id:
            raise ValueError("authorization_id is required")
        plan = self._plan(deployment_input)
        expected_plan = plan_digest(plan)

        existing_release = self.releases.find_by_authorization(authorization_id)
        existing_consumption = self.authorizations.consumption(authorization_id)
        authorization = self.authorizations.authorization(authorization_id)
        if authorization is None:
            raise DeploymentGatewayError("deployment authorization not found")
        if not hmac.compare_digest(authorization.plan_sha256, expected_plan):
            raise DeploymentGatewayError("deployment input does not match authorized plan")

        if existing_release is not None:
            if existing_consumption is None:
                raise DeploymentGatewayError("release exists without authorization consumption evidence")
            if (existing_release.plan_sha256 != existing_consumption.plan_sha256 or
                    existing_release.system_root_sha256 != existing_consumption.system_root_sha256):
                raise DeploymentGatewayError("release/authorization evidence mismatch")
            return DeploymentExecution(authorization_id, True, None, existing_consumption, existing_release)

        if existing_consumption is not None:
            preflight = self._fresh_preflight(
                expected_root=existing_consumption.system_root_sha256,
                max_attempts=max_attempts,
            )
            if not hmac.compare_digest(existing_consumption.plan_sha256, expected_plan):
                raise DeploymentGatewayError("consumed authorization is bound to a different deployment plan")
            release = self.releases.activate(plan, existing_consumption)
            return DeploymentExecution(authorization_id, True, preflight, existing_consumption, release)

        preflight = self._fresh_preflight(expected_root=authorization.system_root_sha256, max_attempts=max_attempts)
        try:
            consumption = self.authorizations.consume(
                authorization_id,
                current_system_root_sha256=preflight.root_after_sha256,
                plan=plan,
            )
        except DeploymentAuthorizationError as exc:
            raise DeploymentGatewayError(str(exc)) from exc
        release = self.releases.activate(plan, consumption)
        return DeploymentExecution(authorization_id, False, preflight, consumption, release)

    def status(self) -> dict[str, Any]:
        return {
            "authorization": self.authorizations.status(),
            "release_backend": self.releases.status(),
            "verified": True,
        }

    def root_component(self) -> dict[str, Any]:
        """Product-state projection safe to include in the system root.

        Outstanding permissions are intentionally excluded: issuing an authorization
        must not mutate the root that authorization is bound to. Activated releases
        are consequential product state and therefore rotate the root.
        """
        return {"release_backend": self.releases.status()}

    @staticmethod
    def prepared_dict(prepared: PreparedDeployment) -> dict[str, Any]:
        return {
            "plan": prepared.plan,
            "preflight": asdict(prepared.preflight),
            "authorization": asdict(prepared.authorization),
        }

    @staticmethod
    def execution_dict(execution: DeploymentExecution) -> dict[str, Any]:
        return {
            "authorization_id": execution.authorization_id,
            "resumed": execution.resumed,
            "preflight": asdict(execution.preflight) if execution.preflight is not None else None,
            "consumption": asdict(execution.consumption),
            "release": asdict(execution.release),
        }
