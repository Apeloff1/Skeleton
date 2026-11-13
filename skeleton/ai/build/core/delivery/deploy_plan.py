"""Compile a manifest + resolved environment into an ordered deploy plan.

Plans are data: a list of steps with explicit preconditions. A runtime
adapter executes them in order and must stop at the first failure, then
apply the attached rollback plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.build.delivery._util import DeliveryError, canonical_json, sha256_json
from skeleton.build.delivery.artifact_manifest import ArtifactManifest
from skeleton.build.delivery.env_config import EnvironmentConfig

STEP_KINDS = (
    "lock", "verify-manifest", "verify-config", "stage", "shift-traffic",
    "health-gate", "bake", "finalize", "unlock",
)


@dataclass(frozen=True)
class DeployStep:
    index: int
    kind: str
    target: str
    params: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "kind": self.kind, "target": self.target, "params": dict(self.params)}


@dataclass(frozen=True)
class DeployPlan:
    environment: str
    release_id: str
    manifest_digest: str
    config_digest: str
    strategy: str
    steps: tuple[DeployStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "release_id": self.release_id,
            "manifest_digest": self.manifest_digest,
            "config_digest": self.config_digest,
            "strategy": self.strategy,
            "steps": [s.to_dict() for s in self.steps],
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict())

    def serialize(self) -> str:
        return canonical_json(self.to_dict() | {"digest": self.digest})


def _traffic_stages(strategy: str, rollout: dict[str, Any], replicas: int) -> list[int]:
    if strategy == "blue-green":
        return [100]
    if strategy == "canary":
        stages = rollout.get("stages", [5, 25, 50, 100])
        if not isinstance(stages, list) or not stages:
            raise DeliveryError("canary stages must be a non-empty list")
        prev = 0
        for pct in stages:
            if isinstance(pct, bool) or not isinstance(pct, int) or not prev < pct <= 100:
                raise DeliveryError("canary stages must strictly increase within 1..100")
            prev = pct
        if stages[-1] != 100:
            raise DeliveryError("canary stages must end at 100")
        return list(stages)
    batch = rollout.get("max_unavailable", 1)
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise DeliveryError("rolling max_unavailable must be >= 1")
    batch = min(batch, replicas)
    stages, done = [], 0
    while done < replicas:
        done = min(replicas, done + batch)
        stages.append(round(done * 100 / replicas))
    return stages


def compile_plan(manifest: ArtifactManifest, env: EnvironmentConfig) -> DeployPlan:
    rollout = dict(env.values["rollout"])
    strategy = rollout["strategy"]
    if env.tier == "production" and manifest.version and "-" in manifest.version:
        raise DeliveryError("prerelease versions cannot deploy to production")
    bake = int(rollout.get("bake_seconds", 0 if env.tier == "dev" else 300))
    steps: list[tuple[str, str, dict[str, Any]]] = [
        ("lock", env.name, {"release_id": manifest.release_id}),
        ("verify-manifest", manifest.release_id, {"digest": manifest.digest}),
        ("verify-config", env.name, {"digest": env.digest}),
        ("stage", "green" if strategy == "blue-green" else "fleet", {"replicas": env.replicas}),
    ]
    for pct in _traffic_stages(strategy, rollout, env.replicas):
        steps.append(("shift-traffic", env.name, {"percent": pct}))
        steps.append(("health-gate", env.name, {"percent": pct}))
        if bake and pct < 100:
            steps.append(("bake", env.name, {"seconds": bake}))
    steps.append(("finalize", env.name, {"release_id": manifest.release_id}))
    steps.append(("unlock", env.name, {}))
    built = tuple(
        DeployStep(i, kind, target, tuple(sorted(params.items())))
        for i, (kind, target, params) in enumerate(steps)
    )
    return DeployPlan(env.name, manifest.release_id, manifest.digest, env.digest, strategy, built)
