"""Deterministic proof packets for empirical claims.

A claim proof is not another confidence score. It is an auditable projection of the
state that currently makes a claim authoritative (or not): truth ledger state,
claim-bound evidence, source ancestry, independence collapse, contradictions,
dependencies, historical knowledge records, calibration references, and the
hierarchical epistemic root. Proof packets are immutable snapshots and can be
verified offline for tampering without trusting the caller that produced them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Any

from core.epistemic_attestation import EpistemicRoot, attest_epistemic_state, verify_epistemic_root
from core.truth_verifier import effective_evidence_quality


CLAIM_PROOF_VERSION = 1


@dataclass(frozen=True, slots=True)
class ClaimProof:
    version: int
    claim: str
    authoritative: bool
    reasons: tuple[str, ...]
    truth_state: dict[str, Any] | None
    evidence: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    independence: dict[str, Any]
    contradiction: dict[str, Any]
    dependencies: tuple[str, ...]
    dependency_blockers: tuple[str, ...]
    knowledge_record_ids: tuple[str, ...]
    calibration_forecast_ids: tuple[str, ...]
    epistemic_root: dict[str, Any]
    generated_at: str
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _normalize_claim(claim: str) -> str:
    value = " ".join(str(claim).split()).strip()
    if not value:
        raise ValueError("claim is required")
    return value


def _source_projection(engine, source_ids: set[str]) -> tuple[dict[str, Any], ...]:
    pending = list(sorted(source_ids)); seen: set[str] = set(); rows: list[dict[str, Any]] = []
    while pending:
        source_id = pending.pop(0)
        if source_id in seen:
            continue
        seen.add(source_id)
        node = engine.source_lineage.get(source_id)
        if node is None:
            rows.append({"source_id": source_id, "registered": False})
            continue
        row = asdict(node)
        row["registered"] = True
        rows.append(row)
        for parent in node.parent_ids:
            if parent not in seen:
                pending.append(parent)
    return tuple(sorted(rows, key=lambda row: str(row.get("source_id", ""))))


def build_claim_proof(engine, claim: str, *, generated_at: str | None = None) -> ClaimProof:
    claim = _normalize_claim(claim)
    stamp = generated_at or datetime.now(UTC).isoformat()
    truth = engine.truth_ledger.get(claim)
    authoritative = bool(engine.truth_ledger.authoritative(claim))
    dependencies = tuple(engine.claim_dependencies.dependencies(claim))
    blockers = tuple(engine.claim_dependencies.blockers(claim, engine.truth_ledger.authoritative))

    records = engine.evidence_registry.records_for(claim, citation_bound_only=False)
    evidence_rows: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for record in records:
        item = record.item
        source_ids.add(item.source_id)
        item_raw = asdict(item); item_raw["kind"] = item.kind.value
        evidence_rows.append({
            "record_id": record.id,
            "registered_at": record.registered_at,
            "citation_bound": record.citation_bound,
            "citation_binding_attestation_sha256": record.citation_binding_attestation_sha256,
            "citation_bound_at": record.citation_bound_at,
            "retracted": record.retracted,
            "retraction_reason": record.retraction_reason,
            "retracted_at": record.retracted_at,
            "effective_quality": effective_evidence_quality(item),
            "item": item_raw,
        })
    evidence_rows.sort(key=lambda row: (str(row["item"].get("source_id", "")), str(row["record_id"])))

    active_evidence = engine.evidence_registry.evidence_for(claim)
    _, independence = engine.independence.collapse(active_evidence)
    independence_raw = {
        "raw_sources": independence.raw_sources,
        "effective_independent_sources": independence.effective_independent_sources,
        "unresolved_sources": list(independence.unresolved_sources),
        "clusters": [
            {
                "id": cluster.id,
                "source_ids": list(cluster.source_ids),
                "reasons": list(cluster.reasons),
                "shared_roots": list(cluster.shared_roots),
                "shared_content_sha256": list(cluster.shared_content_sha256),
            }
            for cluster in independence.clusters
        ],
        "attestation_sha256": independence.attestation_sha256,
    }
    contradiction = engine.contradiction_status(claim)

    knowledge_ids = tuple(sorted(
        record.id for record in engine.fabric.search(claim, limit=100)
        if claim in record.claims
    ))
    forecasts = tuple(sorted(
        row.id for row in engine.calibration.snapshot()
        if row.claim == claim
    ))
    root = attest_epistemic_state(engine.verification_status())
    root_raw = asdict(root)

    reasons: list[str] = []
    if truth is None:
        reasons.append("no_truth_state")
    else:
        if truth.verification_state != "verified": reasons.append("truth_state_not_verified")
        if truth.revoked_at: reasons.append("truth_state_revoked")
        try:
            valid_until = datetime.fromisoformat(truth.valid_until.replace("Z", "+00:00"))
            if valid_until.tzinfo is None or valid_until.astimezone(UTC) <= datetime.now(UTC):
                reasons.append("truth_state_expired")
        except ValueError:
            reasons.append("truth_state_timestamp_invalid")
    if blockers:
        reasons.append("dependency_blocked")
    if contradiction.get("state") == "contested":
        reasons.append("active_empirical_contradiction")
    if not any(row["citation_bound"] and not row["retracted"] for row in evidence_rows):
        reasons.append("no_active_claim_bound_evidence")
    if independence.unresolved_sources:
        reasons.append("unresolved_source_lineage")
    if authoritative and reasons:
        # An authority/proof mismatch is an anomaly, never hidden by the label.
        reasons.append("authority_proof_mismatch")

    payload = {
        "version": CLAIM_PROOF_VERSION,
        "claim": claim,
        "authoritative": authoritative,
        "reasons": tuple(dict.fromkeys(reasons)),
        "truth_state": asdict(truth) if truth is not None else None,
        "evidence": tuple(evidence_rows),
        "sources": _source_projection(engine, source_ids),
        "independence": independence_raw,
        "contradiction": contradiction,
        "dependencies": dependencies,
        "dependency_blockers": blockers,
        "knowledge_record_ids": knowledge_ids,
        "calibration_forecast_ids": forecasts,
        "epistemic_root": root_raw,
        "generated_at": stamp,
    }
    return ClaimProof(**payload, attestation_sha256=_sha(payload))


def verify_claim_proof(proof: ClaimProof) -> bool:
    try:
        root = EpistemicRoot(**proof.epistemic_root)
    except (TypeError, ValueError):
        return False
    if not verify_epistemic_root(root):
        return False
    payload = {
        "version": proof.version,
        "claim": proof.claim,
        "authoritative": proof.authoritative,
        "reasons": proof.reasons,
        "truth_state": proof.truth_state,
        "evidence": proof.evidence,
        "sources": proof.sources,
        "independence": proof.independence,
        "contradiction": proof.contradiction,
        "dependencies": proof.dependencies,
        "dependency_blockers": proof.dependency_blockers,
        "knowledge_record_ids": proof.knowledge_record_ids,
        "calibration_forecast_ids": proof.calibration_forecast_ids,
        "epistemic_root": proof.epistemic_root,
        "generated_at": proof.generated_at,
    }
    return proof.version == CLAIM_PROOF_VERSION and hmac.compare_digest(_sha(payload), proof.attestation_sha256)


def claim_proof_dict(engine, claim: str) -> dict[str, Any]:
    proof = build_claim_proof(engine, claim)
    payload = asdict(proof)
    payload["verified"] = verify_claim_proof(proof)
    return payload
