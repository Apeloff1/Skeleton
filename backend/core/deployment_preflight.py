"""Attested deployment preflight over assurance and epistemic trust.

Trust decisions deliberately avoid Python coercion semantics. Counters must be
non-negative integers (never booleans or numeric strings), booleans must be actual
booleans, roots/attestations must be lowercase SHA-256 digests, and the trust state
must be portable canonical JSON before it can participate in an attestation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_sha256

PREFLIGHT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POSTURES = {"ready", "degraded", "blocked"}


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


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _counter(value: Any, *, finding_id: str, blockers: list[PreflightFinding]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        blockers.append(PreflightFinding(
            finding_id,
            "hard",
            "trust/assurance counter must be a non-negative integer",
        ))
        return 0
    return value


def _finding_valid(value: PreflightFinding, *, severity: str) -> bool:
    return (
        isinstance(value, PreflightFinding)
        and isinstance(value.id, str)
        and bool(value.id.strip())
        and value.severity == severity
        and isinstance(value.detail, str)
        and bool(value.detail.strip())
    )


def _payload(report: DeploymentPreflight) -> dict[str, Any]:
    return {
        "version": report.version,
        "allowed": report.allowed,
        "posture": report.posture,
        "blockers": [asdict(item) for item in report.blockers],
        "warnings": [asdict(item) for item in report.warnings],
        "assurance_attestation_sha256": report.assurance_attestation_sha256,
        "system_root_sha256": report.system_root_sha256,
        "trust_state_sha256": report.trust_state_sha256,
        "finality_required": report.finality_required,
        "finality_satisfied": report.finality_satisfied,
    }


def evaluate_deployment_preflight(
    *,
    assurance: Mapping[str, Any],
    trust: Mapping[str, Any],
    system_root_sha256: str,
) -> DeploymentPreflight:
    if not isinstance(assurance, Mapping) or not isinstance(trust, Mapping):
        raise ValueError("assurance and trust must be mappings")

    blockers: list[PreflightFinding] = []
    warnings: list[PreflightFinding] = []

    hard = _counter(
        assurance.get("hard_failures", 0),
        finding_id="assurance.hard-failures-type",
        blockers=blockers,
    )
    assurance_warnings = _counter(
        assurance.get("warnings", 0),
        finding_id="assurance.warnings-type",
        blockers=blockers,
    )
    posture_raw = assurance.get("posture")
    posture = posture_raw if isinstance(posture_raw, str) and posture_raw else "unknown"
    assurance_attestation = assurance.get("attestation_sha256")
    if not _is_sha(assurance_attestation):
        blockers.append(PreflightFinding(
            "assurance.attestation",
            "hard",
            "assurance attestation is not a canonical SHA-256 digest",
        ))
        assurance_attestation = "0" * 64
    if hard or posture == "blocked":
        blockers.append(PreflightFinding(
            "assurance.blocked",
            "hard",
            f"assurance posture={posture}, hard_failures={hard}",
        ))

    if not _is_sha(system_root_sha256):
        blockers.append(PreflightFinding(
            "system-root.invalid",
            "hard",
            "whole-system root is not a canonical SHA-256 digest",
        ))
        canonical_root = "0" * 64
    else:
        canonical_root = system_root_sha256

    if trust.get("integrity_healthy") is not True:
        blockers.append(PreflightFinding(
            "trust.integrity", "hard", "epistemic trust integrity is not healthy",
        ))

    gossip = _mapping(trust.get("gossip"))
    split_views = _counter(
        gossip.get("split_views", 0), finding_id="trust.split-view-type", blockers=blockers,
    )
    rollbacks = _counter(
        gossip.get("rollbacks", 0), finding_id="trust.rollback-type", blockers=blockers,
    )
    if split_views:
        blockers.append(PreflightFinding(
            "trust.split-view", "hard", f"{split_views} split-view incident(s)",
        ))
    if rollbacks:
        blockers.append(PreflightFinding(
            "trust.rollback", "hard", f"{rollbacks} rollback incident(s)",
        ))

    witnesses = _mapping(trust.get("witnesses"))
    equivocations = _counter(
        witnesses.get("equivocations", 0),
        finding_id="trust.witness-equivocation-type",
        blockers=blockers,
    )
    if equivocations:
        blockers.append(PreflightFinding(
            "trust.witness-equivocation",
            "hard",
            f"{equivocations} trusted witness equivocation incident(s)",
        ))

    signed = _mapping(trust.get("signed_witnesses"))
    signed_equivocations = _counter(
        signed.get("equivocations", 0),
        finding_id="trust.signed-witness-equivocation-type",
        blockers=blockers,
    )
    if signed_equivocations:
        blockers.append(PreflightFinding(
            "trust.signed-witness-equivocation",
            "hard",
            f"{signed_equivocations} signed witness equivocation incident(s)",
        ))

    policy = _mapping(trust.get("policy"))
    normal_required = policy.get("finality_required") is True
    signed_required = policy.get("signed_finality_required") is True
    finality_required = normal_required or signed_required
    quorum_capable = policy.get("quorum_capable") is True
    signed_quorum_capable = policy.get("signed_quorum_capable") is True
    finality_satisfied = trust.get("finality_satisfied") is True

    if normal_required and not quorum_capable:
        blockers.append(PreflightFinding(
            "finality.quorum-capability",
            "hard",
            "configured witness groups cannot satisfy required quorum",
        ))
    if signed_required and not signed_quorum_capable:
        blockers.append(PreflightFinding(
            "finality.signed-quorum-capability",
            "hard",
            "pinned Ed25519 witness groups cannot satisfy required signed quorum",
        ))
    if finality_required and not finality_satisfied:
        blockers.append(PreflightFinding(
            "finality.current-head",
            "hard",
            "current epistemic transparency head is not required-finality complete",
        ))
    elif not finality_required and not finality_satisfied:
        warnings.append(PreflightFinding(
            "finality.current-head",
            "warning",
            "current epistemic transparency head is published but not quorum-finalized",
        ))
    if not finality_required and not quorum_capable:
        warnings.append(PreflightFinding(
            "finality.quorum-capability",
            "warning",
            "configured witness groups cannot currently satisfy finality quorum",
        ))

    current = _mapping(trust.get("current_head"))
    tree_size = _counter(
        current.get("current_tree_size", 0),
        finding_id="transparency.tree-size-type",
        blockers=blockers,
    )
    if tree_size < 1:
        warnings.append(PreflightFinding(
            "transparency.empty", "warning", "no epistemic transparency checkpoint has been published",
        ))
    if assurance_warnings:
        warnings.append(PreflightFinding(
            "assurance.warnings",
            "warning",
            f"assurance reports {assurance_warnings} warning invariant(s)",
        ))

    try:
        trust_sha = _sha(dict(trust))
    except CanonicalJSONError:
        blockers.append(PreflightFinding(
            "trust.state-noncanonical",
            "hard",
            "epistemic trust state is not portable canonical JSON",
        ))
        trust_sha = _sha({"invalid_trust_state": True})

    allowed = not blockers
    result_posture = "blocked" if blockers else ("degraded" if warnings else "ready")
    draft = DeploymentPreflight(
        PREFLIGHT_VERSION,
        allowed,
        result_posture,
        tuple(blockers),
        tuple(warnings),
        assurance_attestation,
        canonical_root,
        trust_sha,
        finality_required,
        finality_satisfied,
        "",
    )
    attestation = _sha(_payload(draft))
    return DeploymentPreflight(
        draft.version,
        draft.allowed,
        draft.posture,
        draft.blockers,
        draft.warnings,
        draft.assurance_attestation_sha256,
        draft.system_root_sha256,
        draft.trust_state_sha256,
        draft.finality_required,
        draft.finality_satisfied,
        attestation,
    )


def verify_deployment_preflight(report: DeploymentPreflight) -> bool:
    try:
        if not isinstance(report, DeploymentPreflight):
            return False
        if isinstance(report.version, bool) or report.version != PREFLIGHT_VERSION:
            return False
        if not isinstance(report.allowed, bool) or not isinstance(report.finality_required, bool) or not isinstance(report.finality_satisfied, bool):
            return False
        if report.posture not in _POSTURES:
            return False
        if not isinstance(report.blockers, tuple) or not isinstance(report.warnings, tuple):
            return False
        if not all(_finding_valid(item, severity="hard") for item in report.blockers):
            return False
        if not all(_finding_valid(item, severity="warning") for item in report.warnings):
            return False
        if not all(_is_sha(value) for value in (
            report.assurance_attestation_sha256,
            report.system_root_sha256,
            report.trust_state_sha256,
            report.attestation_sha256,
        )):
            return False
        expected_allowed = not report.blockers
        expected_posture = "blocked" if report.blockers else ("degraded" if report.warnings else "ready")
        if report.allowed != expected_allowed or report.posture != expected_posture:
            return False
        if report.finality_required and not report.finality_satisfied:
            if "finality.current-head" not in {item.id for item in report.blockers}:
                return False
        return hmac.compare_digest(_sha(_payload(report)), report.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False
