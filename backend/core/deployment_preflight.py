"""Attested deployment preflight over assurance and epistemic trust.

Deployment is a stronger decision than runtime health. This gate turns assurance,
transparency integrity, witness quorum policy and current-head finality into an
explicit, deterministic decision record. It never upgrades trust: missing evidence
is a blocker when policy requires it and otherwise remains visible as a warning.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
from typing import Any, Mapping

PREFLIGHT_VERSION = 1


@dataclass(frozen=True, slots=True)
class PreflightFinding:
    id: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class DeploymentPreflight:
    version: int
    allowed: bool
    posture: str
    blockers: tuple[PreflightFinding, ...]
    warnings: tuple[PreflightFinding, ...]
    assurance_attestation_sha256: str
    system_root_sha256: str
    trust_state_sha256: str
    finality_required: bool
    finality_satisfied: bool
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _trust_digest(trust: Mapping[str, Any]) -> str:
    return _sha(dict(trust))


def evaluate_deployment_preflight(*, assurance: Mapping[str, Any], trust: Mapping[str, Any],
                                  system_root_sha256: str) -> DeploymentPreflight:
    blockers: list[PreflightFinding] = []; warnings: list[PreflightFinding] = []
    hard_failures = int(assurance.get("hard_failures", 0) or 0)
    assurance_posture = str(assurance.get("posture") or "unknown")
    assurance_attestation = str(assurance.get("attestation_sha256") or "")
    if hard_failures or assurance_posture == "blocked":
        blockers.append(PreflightFinding("assurance.blocked", "hard",
                                         f"assurance posture={assurance_posture}, hard_failures={hard_failures}"))

    if trust.get("integrity_healthy") is not True:
        blockers.append(PreflightFinding("trust.integrity", "hard", "epistemic trust integrity is not healthy"))

    gossip = trust.get("gossip") if isinstance(trust.get("gossip"), Mapping) else {}
    split_views = int(gossip.get("split_views", 0) or 0); rollbacks = int(gossip.get("rollbacks", 0) or 0)
    if split_views:
        blockers.append(PreflightFinding("trust.split-view", "hard", f"{split_views} split-view incident(s)"))
    if rollbacks:
        blockers.append(PreflightFinding("trust.rollback", "hard", f"{rollbacks} rollback incident(s)"))

    witnesses = trust.get("witnesses") if isinstance(trust.get("witnesses"), Mapping) else {}
    equivocations = int(witnesses.get("equivocations", 0) or 0)
    if equivocations:
        blockers.append(PreflightFinding("trust.witness-equivocation", "hard",
                                         f"{equivocations} trusted witness equivocation incident(s)"))

    policy = trust.get("policy") if isinstance(trust.get("policy"), Mapping) else {}
    finality_required = policy.get("finality_required") is True
    quorum_capable = policy.get("quorum_capable") is True
    finality_satisfied = trust.get("finality_satisfied") is True
    if finality_required and not quorum_capable:
        blockers.append(PreflightFinding("finality.quorum-capability", "hard",
                                         "finality is required but configured witness groups cannot satisfy quorum"))
    if finality_required and not finality_satisfied:
        blockers.append(PreflightFinding("finality.current-head", "hard",
                                         "current epistemic transparency head is not quorum-finalized"))
    elif not finality_required and not finality_satisfied:
        warnings.append(PreflightFinding("finality.current-head", "warning",
                                         "current epistemic transparency head is published but not quorum-finalized"))
    if not finality_required and not quorum_capable:
        warnings.append(PreflightFinding("finality.quorum-capability", "warning",
                                         "configured witness groups cannot currently satisfy finality quorum"))

    current = trust.get("current_head") if isinstance(trust.get("current_head"), Mapping) else {}
    if int(current.get("current_tree_size", 0) or 0) < 1:
        warnings.append(PreflightFinding("transparency.empty", "warning", "no epistemic transparency checkpoint has been published"))

    assurance_warnings = int(assurance.get("warnings", 0) or 0)
    if assurance_warnings:
        warnings.append(PreflightFinding("assurance.warnings", "warning",
                                         f"assurance reports {assurance_warnings} warning invariant(s)"))

    allowed = not blockers
    posture = "blocked" if blockers else ("degraded" if warnings else "ready")
    trust_sha = _trust_digest(trust)
    payload = {
        "version": PREFLIGHT_VERSION, "allowed": allowed, "posture": posture,
        "blockers": [asdict(x) for x in blockers], "warnings": [asdict(x) for x in warnings],
        "assurance_attestation_sha256": assurance_attestation,
        "system_root_sha256": str(system_root_sha256), "trust_state_sha256": trust_sha,
        "finality_required": finality_required, "finality_satisfied": finality_satisfied,
    }
    return DeploymentPreflight(
        PREFLIGHT_VERSION, allowed, posture, tuple(blockers), tuple(warnings),
        assurance_attestation, str(system_root_sha256), trust_sha,
        finality_required, finality_satisfied, _sha(payload),
    )


def verify_deployment_preflight(report: DeploymentPreflight) -> bool:
    payload = {
        "version": report.version, "allowed": report.allowed, "posture": report.posture,
        "blockers": [asdict(x) for x in report.blockers], "warnings": [asdict(x) for x in report.warnings],
        "assurance_attestation_sha256": report.assurance_attestation_sha256,
        "system_root_sha256": report.system_root_sha256, "trust_state_sha256": report.trust_state_sha256,
        "finality_required": report.finality_required, "finality_satisfied": report.finality_satisfied,
    }
    return report.version == PREFLIGHT_VERSION and hmac.compare_digest(_sha(payload), report.attestation_sha256)
