"""Algorithm-agile, predecessor-linked execution receipts.

This module is deliberately network-independent. It wraps immutable execution
commitments without changing the historical receipt they attest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
from typing import Final, Mapping

RECEIPT_SCHEMA: Final = "skeleton.ai.execution-receipt.v1"
SUPPORTED_DIGESTS: Final = ("sha256", "sha3-256", "blake2b-256")

def canonical_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")

def digest_bytes(payload: bytes, algorithm: str) -> str:
    if algorithm == "sha256":
        return hashlib.sha256(payload).hexdigest()
    if algorithm == "sha3-256":
        return hashlib.sha3_256(payload).hexdigest()
    if algorithm == "blake2b-256":
        return hashlib.blake2b(payload, digest_size=32).hexdigest()
    raise ValueError("unsupported digest algorithm")

def require_digest(value: str, name: str) -> str:
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase 256-bit hex")
    return value

@dataclass(frozen=True, slots=True)
class ProofAttestation:
    proof_type: str
    verifier_id: str
    evidence_digest: str
    algorithm: str = "sha256"

    def __post_init__(self) -> None:
        if not self.proof_type.strip() or not self.verifier_id.strip():
            raise ValueError("proof identity must be non-empty")
        if self.algorithm not in SUPPORTED_DIGESTS:
            raise ValueError("unsupported proof digest algorithm")
        require_digest(self.evidence_digest,"evidence_digest")

    def to_dict(self) -> dict[str,str]:
        return {"proof_type":self.proof_type,"verifier_id":self.verifier_id,"algorithm":self.algorithm,"evidence_digest":self.evidence_digest}

@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    semantic_request_digest: str
    runtime_receipt_digest: str
    context_digest: str | None = None
    admission_policy_digest: str | None = None
    predecessor_digest: str | None = None
    digest_algorithm: str = "sha256"
    proofs: tuple[ProofAttestation,...] = field(default_factory=tuple)
    schema: str = RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != RECEIPT_SCHEMA:
            raise ValueError("unsupported execution receipt schema")
        if self.digest_algorithm not in SUPPORTED_DIGESTS:
            raise ValueError("unsupported receipt digest algorithm")
        require_digest(self.semantic_request_digest,"semantic_request_digest")
        require_digest(self.runtime_receipt_digest,"runtime_receipt_digest")
        for name in ("context_digest","admission_policy_digest","predecessor_digest"):
            value=getattr(self,name)
            if value is not None:
                require_digest(value,name)
        proofs=tuple(self.proofs)
        identities=[(p.proof_type,p.verifier_id) for p in proofs]
        if len(identities)!=len(set(identities)):
            raise ValueError("proof identities must be unique")
        object.__setattr__(self,"proofs",proofs)

    def commitment_dict(self) -> dict[str,object]:
        return {
            "schema":self.schema,
            "digest_algorithm":self.digest_algorithm,
            "semantic_request_digest":self.semantic_request_digest,
            "runtime_receipt_digest":self.runtime_receipt_digest,
            "context_digest":self.context_digest,
            "admission_policy_digest":self.admission_policy_digest,
            "predecessor_digest":self.predecessor_digest,
            "proofs":[proof.to_dict() for proof in sorted(self.proofs,key=lambda p:(p.proof_type,p.verifier_id))],
        }

    @property
    def digest(self) -> str:
        return digest_bytes(canonical_bytes(self.commitment_dict()),self.digest_algorithm)

    def verify_offline(self, *, expected_predecessor: str | None = None) -> bool:
        try:
            require_digest(self.digest,"receipt digest")
        except ValueError:
            return False
        if expected_predecessor is not None:
            try:
                require_digest(expected_predecessor,"expected_predecessor")
            except ValueError:
                return False
            if self.predecessor_digest is None or not hmac.compare_digest(self.predecessor_digest,expected_predecessor):
                return False
        return True

    def reattest(self, *, algorithm: str, proofs: tuple[ProofAttestation,...]=()) -> "ExecutionReceipt":
        if algorithm not in SUPPORTED_DIGESTS:
            raise ValueError("unsupported receipt digest algorithm")
        return ExecutionReceipt(
            semantic_request_digest=self.semantic_request_digest,
            runtime_receipt_digest=self.runtime_receipt_digest,
            context_digest=self.context_digest,
            admission_policy_digest=self.admission_policy_digest,
            predecessor_digest=self.digest,
            digest_algorithm=algorithm,
            proofs=proofs,
        )

def verify_chain(receipts: tuple[ExecutionReceipt,...]) -> bool:
    if not receipts:
        return False
    if receipts[0].predecessor_digest is not None:
        return False
    for previous,current in zip(receipts,receipts[1:]):
        if not current.verify_offline(expected_predecessor=previous.digest):
            return False
        if current.semantic_request_digest != previous.semantic_request_digest:
            return False
        if current.runtime_receipt_digest != previous.runtime_receipt_digest:
            return False
        if current.context_digest != previous.context_digest:
            return False
        if current.admission_policy_digest != previous.admission_policy_digest:
            return False
    return all(receipt.verify_offline() for receipt in receipts)

__all__=["ExecutionReceipt","ProofAttestation","RECEIPT_SCHEMA","SUPPORTED_DIGESTS","canonical_bytes","digest_bytes","verify_chain"]
