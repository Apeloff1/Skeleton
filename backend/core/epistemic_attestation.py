"""Hierarchical attestation for the empirical knowledge subsystem.

A truth system should expose one deterministic identity for the state that made a
claim authoritative. The root binds the durable evidence registry, source lineage,
claim truth ledger, dependency graph, calibration ledger, four-surface knowledge
catalog, and the verification policy/safety flags. Component hashes remain visible
so operators can identify which trust domain changed without weakening the root.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import re
from typing import Any


EPISTEMIC_ROOT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EpistemicAttestationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EpistemicRoot:
    version: int
    components: dict[str, str]
    policy_sha256: str
    safety_sha256: str
    root_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: Any, field: str) -> str:
    value = str(value or "").strip().lower()
    if not _SHA256.fullmatch(value):
        raise EpistemicAttestationError(f"{field} missing or invalid sha256")
    return value


def attest_epistemic_state(verification: dict[str, Any]) -> EpistemicRoot:
    if not isinstance(verification, dict):
        raise EpistemicAttestationError("verification status must be an object")

    registry = verification.get("evidence_registry") if isinstance(verification.get("evidence_registry"), dict) else {}
    lineage = verification.get("source_lineage") if isinstance(verification.get("source_lineage"), dict) else {}
    truth = verification.get("truth_ledger") if isinstance(verification.get("truth_ledger"), dict) else {}
    dependencies = verification.get("claim_dependencies") if isinstance(verification.get("claim_dependencies"), dict) else {}
    calibration = verification.get("calibration") if isinstance(verification.get("calibration"), dict) else {}
    knowledge = verification.get("knowledge") if isinstance(verification.get("knowledge"), dict) else {}
    policy = verification.get("verification_policy") if isinstance(verification.get("verification_policy"), dict) else {}

    components = {
        "evidence_registry": _digest(registry.get("sha256"), "evidence_registry"),
        "source_lineage": _digest(lineage.get("sha256"), "source_lineage"),
        "truth_ledger": _digest(truth.get("sha256"), "truth_ledger"),
        "claim_dependencies": _digest(dependencies.get("sha256"), "claim_dependencies"),
        "calibration": _digest(calibration.get("sha256"), "calibration"),
        "knowledge_catalog": _digest(knowledge.get("catalog_sha256"), "knowledge_catalog"),
    }
    safety = {
        "truth_gated": verification.get("truth_gated") is True,
        "speculation_authoritative": verification.get("speculation_authoritative") is True,
        "model_consensus_is_empirical_evidence": verification.get("model_consensus_is_empirical_evidence") is True,
        "semantic_similarity_is_truth_identity": verification.get("semantic_similarity_is_truth_identity") is True,
        "truth_eligible_default": registry.get("truth_eligible_default") is True,
        "evidence_process_safe": registry.get("cross_process_locking") is True,
        "lineage_process_safe": lineage.get("cross_process_locking") is True,
        "truth_process_safe": truth.get("cross_process_locking") is True,
        "dependency_process_safe": dependencies.get("cross_process_locking") is True,
        "calibration_process_safe": calibration.get("cross_process_locking") is True,
        "knowledge_process_safe": knowledge.get("cross_process_locking") is True,
    }
    policy_sha256 = _sha(policy)
    safety_sha256 = _sha(safety)
    payload = {
        "version": EPISTEMIC_ROOT_VERSION,
        "components": components,
        "policy_sha256": policy_sha256,
        "safety_sha256": safety_sha256,
    }
    return EpistemicRoot(
        version=EPISTEMIC_ROOT_VERSION,
        components=components,
        policy_sha256=policy_sha256,
        safety_sha256=safety_sha256,
        root_sha256=_sha(payload),
    )


def verify_epistemic_root(root: EpistemicRoot) -> bool:
    try:
        components = {key: _digest(value, key) for key, value in root.components.items()}
        policy_sha256 = _digest(root.policy_sha256, "policy_sha256")
        safety_sha256 = _digest(root.safety_sha256, "safety_sha256")
        claimed = _digest(root.root_sha256, "root_sha256")
    except EpistemicAttestationError:
        return False
    payload = {
        "version": int(root.version),
        "components": components,
        "policy_sha256": policy_sha256,
        "safety_sha256": safety_sha256,
    }
    return root.version == EPISTEMIC_ROOT_VERSION and hmac.compare_digest(_sha(payload), claimed)


def epistemic_root_dict(verification: dict[str, Any]) -> dict[str, Any]:
    root = attest_epistemic_state(verification)
    payload = asdict(root)
    payload["verified"] = verify_epistemic_root(root)
    return payload
