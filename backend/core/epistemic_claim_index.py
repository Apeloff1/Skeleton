"""Merkle authority index for claim-level epistemic state.

Global file checksums prove storage integrity but cannot prove that one claim belongs
to the committed state. This index derives one canonical authority leaf per known
claim and commits the leaves into a sparse Merkle root. Proofs therefore support
both membership and non-membership against the same epistemic root.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Any

from core.sparse_merkle import build_sparse_proof, sparse_merkle_root
from core.truth_verifier import effective_evidence_quality

CLAIM_INDEX_VERSION = 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _norm(claim: str) -> str:
    return " ".join(str(claim).split()).strip()


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
        raw = asdict(node); raw["registered"] = True; rows.append(raw)
        for parent in node.parent_ids:
            if parent not in seen:
                pending.append(parent)
    return tuple(sorted(rows, key=lambda row: str(row.get("source_id", ""))))


def claim_authority_payload(engine, claim: str) -> dict[str, Any]:
    claim = _norm(claim)
    if not claim:
        raise ValueError("claim is required")
    truth = engine.truth_ledger.get(claim)
    records = engine.evidence_registry.records_for(claim, citation_bound_only=False)
    evidence: list[dict[str, Any]] = []; source_ids: set[str] = set()
    for record in records:
        item = record.item; source_ids.add(item.source_id)
        item_raw = asdict(item); item_raw["kind"] = item.kind.value
        evidence.append({
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
    evidence.sort(key=lambda row: (str(row["item"].get("source_id", "")), str(row["record_id"])))

    eligible = engine.evidence_registry.evidence_for(claim)
    _, independence = engine.independence.collapse(eligible)
    independence_raw = {
        "raw_sources": independence.raw_sources,
        "effective_independent_sources": independence.effective_independent_sources,
        "unresolved_sources": list(independence.unresolved_sources),
        "clusters": [{
            "id": row.id, "source_ids": list(row.source_ids), "reasons": list(row.reasons),
            "shared_roots": list(row.shared_roots), "shared_content_sha256": list(row.shared_content_sha256),
        } for row in independence.clusters],
        "attestation_sha256": independence.attestation_sha256,
    }
    dependencies = tuple(engine.claim_dependencies.dependencies(claim))
    dependency_states = []
    for dependency in dependencies:
        state = engine.truth_ledger.get(dependency)
        dependency_states.append({
            "claim": dependency,
            "authoritative": engine.truth_ledger.authoritative(dependency),
            "truth_state": asdict(state) if state is not None else None,
        })
    contradiction = engine.contradiction_status(claim)
    payload = {
        "version": CLAIM_INDEX_VERSION,
        "claim": claim,
        "authoritative": bool(engine.truth_ledger.authoritative(claim)),
        "truth_state": asdict(truth) if truth is not None else None,
        "evidence": evidence,
        "sources": _source_projection(engine, source_ids),
        "independence": independence_raw,
        "dependencies": list(dependencies),
        "dependency_states": dependency_states,
        "contradiction": contradiction,
    }
    payload["state_sha256"] = _sha(payload)
    return payload


class EpistemicClaimIndex:
    def __init__(self, engine) -> None:
        self.engine = engine

    def known_claims(self) -> tuple[str, ...]:
        claims = set(self.engine.evidence_registry.all_claims())
        claims.update(row.claim for row in self.engine.truth_ledger.snapshot())
        for row in self.engine.claim_dependencies.snapshot():
            claims.add(row.claim); claims.update(row.depends_on)
        return tuple(sorted((_norm(x) for x in claims if _norm(x)), key=str.casefold))

    def mapping(self) -> dict[str, dict[str, Any]]:
        return {claim: claim_authority_payload(self.engine, claim) for claim in self.known_claims()}

    def root_sha256(self) -> str:
        return sparse_merkle_root(self.mapping())

    def proof(self, claim: str) -> dict[str, Any]:
        return asdict(build_sparse_proof(self.mapping(), _norm(claim)))

    def stats(self) -> dict[str, Any]:
        mapping = self.mapping()
        return {
            "version": CLAIM_INDEX_VERSION,
            "claims": len(mapping),
            "authoritative": sum(bool(value.get("authoritative")) for value in mapping.values()),
            "merkle_root_sha256": sparse_merkle_root(mapping),
            "proof_scheme": "sparse-merkle-sha256-256",
            "membership_and_absence_proofs": True,
        }
