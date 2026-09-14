"""Portable, freshness-bounded claim proofs with sparse-Merkle membership.

Unlike the compatibility ClaimProof, a PortableClaimProof can be verified against
an externally pinned authority root or checkpoint. This separates three questions:
1) is the packet internally intact, 2) is the claim a member/absence of the committed
state, and 3) does that state match a root trusted outside the packet itself?
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import re
from typing import Any, Mapping

from core.claim_proof import ClaimProof, build_claim_proof, verify_claim_proof
from core.epistemic_attestation import attest_epistemic_state
from core.epistemic_checkpoint import CHECKPOINT_VERSION, EpistemicCheckpoint, EpistemicCheckpointLedger
from core.epistemic_claim_index import EpistemicClaimIndex
from core.sparse_merkle import TREE_VERSION, proof_from_dict, verify_sparse_proof

PORTABLE_PROOF_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PortableClaimProof:
    version: int
    claim: str
    claim_proof: dict[str, Any]
    authority_proof: dict[str, Any]
    authority_root_sha256: str
    epistemic_root_sha256: str
    checkpoint: dict[str, Any] | None
    generated_at: str
    valid_until: str
    revocation_witness_sha256: str
    packet_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse(stamp: str) -> datetime:
    value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("portable proof timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _checkpoint_hash(raw: Mapping[str, Any]) -> str:
    payload = {
        "version": int(raw.get("version", 0)),
        "sequence": int(raw.get("sequence", 0)),
        "authority_root_sha256": str(raw.get("authority_root_sha256", "")),
        "epistemic_root_sha256": str(raw.get("epistemic_root_sha256", "")),
        "observed_at": str(raw.get("observed_at", "")),
        "previous_sha256": str(raw.get("previous_sha256", "")),
    }
    return _sha(payload)


def _revocation_witness(claim_proof: ClaimProof) -> str:
    truth = claim_proof.truth_state or {}
    revoked_at = str(truth.get("revoked_at") or "")
    if not revoked_at:
        return ""
    retracted_ids = sorted(str(row.get("record_id")) for row in claim_proof.evidence if row.get("retracted"))
    return _sha({
        "claim": claim_proof.claim,
        "revoked_at": revoked_at,
        "revocation_reason": str(truth.get("revocation_reason") or ""),
        "retracted_evidence_record_ids": retracted_ids,
    })


def _packet_payload(*, claim: str, claim_proof: dict[str, Any], authority_proof: dict[str, Any],
                    authority_root_sha256: str, epistemic_root_sha256: str,
                    checkpoint: dict[str, Any] | None, generated_at: str, valid_until: str,
                    revocation_witness_sha256: str) -> dict[str, Any]:
    return {
        "version": PORTABLE_PROOF_VERSION,
        "claim": claim,
        "claim_proof": claim_proof,
        "authority_proof": authority_proof,
        "authority_root_sha256": authority_root_sha256,
        "epistemic_root_sha256": epistemic_root_sha256,
        "checkpoint": checkpoint,
        "generated_at": generated_at,
        "valid_until": valid_until,
        "revocation_witness_sha256": revocation_witness_sha256,
    }


def build_portable_claim_proof(engine, claim: str, *, checkpoint_ledger: EpistemicCheckpointLedger | None = None,
                               generated_at: str | None = None, max_age_seconds: int = 900) -> PortableClaimProof:
    if max_age_seconds < 1 or max_age_seconds > 86400:
        raise ValueError("max_age_seconds must be between 1 and 86400")
    stamp = generated_at or datetime.now(UTC).isoformat()
    issued = _parse(stamp)
    compatibility = build_claim_proof(engine, claim, generated_at=stamp)
    index = EpistemicClaimIndex(engine)
    authority_proof = index.proof(compatibility.claim)
    authority_root = str(authority_proof["root_sha256"])
    epistemic_root = attest_epistemic_state(engine.verification_status())

    expiry = issued + timedelta(seconds=max_age_seconds)
    truth = compatibility.truth_state or {}
    truth_valid_until = str(truth.get("valid_until") or "")
    if compatibility.authoritative and truth_valid_until:
        expiry = min(expiry, _parse(truth_valid_until))

    checkpoint_raw: dict[str, Any] | None = None
    if checkpoint_ledger is not None:
        checkpoint = checkpoint_ledger.record(
            authority_root_sha256=authority_root,
            epistemic_root_sha256=epistemic_root.root_sha256,
            observed_at=stamp,
        )
        checkpoint_raw = asdict(checkpoint)

    compatibility_raw = asdict(compatibility)
    revocation = _revocation_witness(compatibility)
    payload = _packet_payload(
        claim=compatibility.claim, claim_proof=compatibility_raw, authority_proof=authority_proof,
        authority_root_sha256=authority_root, epistemic_root_sha256=epistemic_root.root_sha256,
        checkpoint=checkpoint_raw, generated_at=stamp, valid_until=expiry.isoformat(),
        revocation_witness_sha256=revocation,
    )
    return PortableClaimProof(**payload, packet_sha256=_sha(payload))


def verify_portable_claim_proof(packet: PortableClaimProof, *, now: datetime | None = None,
                                expected_authority_root: str | None = None,
                                expected_checkpoint_sha256: str | None = None,
                                require_checkpoint: bool = False) -> bool:
    if packet.version != PORTABLE_PROOF_VERSION:
        return False
    if not _SHA256.fullmatch(str(packet.authority_root_sha256)) or not _SHA256.fullmatch(str(packet.epistemic_root_sha256)):
        return False
    try:
        compatibility = ClaimProof(**packet.claim_proof)
        sparse = proof_from_dict(packet.authority_proof)
        issued = _parse(packet.generated_at); expires = _parse(packet.valid_until)
    except (TypeError, ValueError, KeyError):
        return False
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return False
    current = current.astimezone(UTC)
    if expires < issued or current > expires:
        return False
    if not verify_claim_proof(compatibility) or not verify_sparse_proof(sparse):
        return False
    if sparse.version != TREE_VERSION or sparse.key != packet.claim or compatibility.claim != packet.claim:
        return False
    if sparse.root_sha256 != packet.authority_root_sha256:
        return False
    if expected_authority_root is not None and not hmac.compare_digest(packet.authority_root_sha256, str(expected_authority_root)):
        return False

    if sparse.present:
        value = sparse.value if isinstance(sparse.value, dict) else {}
        if value.get("claim") != packet.claim or bool(value.get("authoritative")) != compatibility.authoritative:
            return False
        if value.get("truth_state") != compatibility.truth_state:
            return False
        if tuple(value.get("dependencies") or ()) != compatibility.dependencies:
            return False
        value_evidence = tuple(value.get("evidence") or ())
        if value_evidence != compatibility.evidence:
            return False
        if tuple(value.get("sources") or ()) != compatibility.sources:
            return False
        if value.get("independence") != compatibility.independence:
            return False
    else:
        if compatibility.authoritative or compatibility.truth_state is not None or compatibility.evidence:
            return False

    witness = _revocation_witness(compatibility)
    if not hmac.compare_digest(witness, packet.revocation_witness_sha256):
        return False

    if require_checkpoint and packet.checkpoint is None:
        return False
    if packet.checkpoint is not None:
        checkpoint = packet.checkpoint
        if int(checkpoint.get("version", 0)) != CHECKPOINT_VERSION:
            return False
        claimed = str(checkpoint.get("sha256", ""))
        if not _SHA256.fullmatch(claimed) or not hmac.compare_digest(_checkpoint_hash(checkpoint), claimed):
            return False
        if checkpoint.get("authority_root_sha256") != packet.authority_root_sha256:
            return False
        if checkpoint.get("epistemic_root_sha256") != packet.epistemic_root_sha256:
            return False
        if expected_checkpoint_sha256 is not None and not hmac.compare_digest(claimed, str(expected_checkpoint_sha256)):
            return False
    elif expected_checkpoint_sha256 is not None:
        return False

    payload = _packet_payload(
        claim=packet.claim, claim_proof=packet.claim_proof, authority_proof=packet.authority_proof,
        authority_root_sha256=packet.authority_root_sha256, epistemic_root_sha256=packet.epistemic_root_sha256,
        checkpoint=packet.checkpoint, generated_at=packet.generated_at, valid_until=packet.valid_until,
        revocation_witness_sha256=packet.revocation_witness_sha256,
    )
    return hmac.compare_digest(_sha(payload), packet.packet_sha256)


def portable_claim_proof_dict(engine, claim: str, *, checkpoint_ledger: EpistemicCheckpointLedger | None = None,
                              max_age_seconds: int = 900) -> dict[str, Any]:
    packet = build_portable_claim_proof(engine, claim, checkpoint_ledger=checkpoint_ledger,
                                        max_age_seconds=max_age_seconds)
    payload = asdict(packet)
    payload["self_verified"] = verify_portable_claim_proof(packet)
    payload["trust_note"] = "Pin authority_root_sha256 or checkpoint.sha256 outside this packet for independent trust."
    return payload
