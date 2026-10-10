"""Decade-horizon signals for long-lived AI execution and provenance contracts.

These are engineering migration horizons, not forecasts. They keep durable
receipts explicit about which evolution seams must remain available as
cryptography, model runtimes, storage and verification mechanisms change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SIGNAL_SCHEMA = "skeleton.ai.horizon-signals.v1"
_VALID_DECADES: Final = tuple(range(2020, 2100, 10))

@dataclass(frozen=True, slots=True)
class HorizonSignal:
    decade: int
    signal_id: str
    domain: str
    requirement: str
    compatibility_rule: str

    def __post_init__(self) -> None:
        if self.decade not in _VALID_DECADES:
            raise ValueError("decade must be a supported ten-year horizon")
        for name in ("signal_id", "domain", "requirement", "compatibility_rule"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.signal_id.startswith(f"h{self.decade}."):
            raise ValueError("signal_id must be namespaced to its decade")

    def as_dict(self) -> dict[str, object]:
        return {
            "decade": self.decade,
            "signal_id": self.signal_id,
            "domain": self.domain,
            "requirement": self.requirement,
            "compatibility_rule": self.compatibility_rule,
        }

SIGNALS: Final[tuple[HorizonSignal, ...]] = (
    HorizonSignal(2020,"h2020.content-addressing","provenance","Bind model, tokenizer, context, request and output to deterministic digests.","Never reinterpret an existing digest under a different canonicalization."),
    HorizonSignal(2020,"h2020.replay","runtime","Emit deterministic replay receipts for admitted native inference.","Replay verification must fail closed on identity or output mismatch."),
    HorizonSignal(2030,"h2030.algorithm-agility","cryptography","Carry explicit digest and signature algorithm identities beside durable seals.","New algorithms may be added; an existing algorithm identifier may never change meaning."),
    HorizonSignal(2030,"h2030.multi-runtime","runtime","Separate semantic request identity from device and runtime implementation identity.","Runtime migration must preserve request lineage while issuing a new execution receipt."),
    HorizonSignal(2040,"h2040.provenance-portability","provenance","Use self-describing canonical receipts that can be verified outside the originating process.","Portable verification must not require mutable application state."),
    HorizonSignal(2040,"h2040.lineage-graph","context","Preserve derivation edges for compaction, summarization and transformed evidence.","Derived artifacts must retain transitive custody of original source identities."),
    HorizonSignal(2050,"h2050.archive-verification","storage","Retain canonical bytes or sufficient immutable commitments for long-horizon verification.","Archival migration may change storage encoding but not committed semantic identity."),
    HorizonSignal(2050,"h2050.receipt-upconversion","contracts","Support explicit version-to-version receipt migration with preserved predecessor digests.","Migration creates a new receipt and must never rewrite the predecessor."),
    HorizonSignal(2060,"h2060.heterogeneous-proof","verification","Permit multiple independent proof mechanisms to attest one execution lineage.","Additional proofs augment rather than silently replace historical verification evidence."),
    HorizonSignal(2060,"h2060.offline-verification","verification","Keep core provenance verification deterministic and network-independent.","Loss of an external service must not make canonical historical receipts unverifiable."),
    HorizonSignal(2070,"h2070.identity-continuity","identity","Distinguish enduring semantic identities from replaceable implementations and locations.","Relocation, re-sharding or hardware replacement cannot mutate semantic lineage."),
    HorizonSignal(2070,"h2070.policy-history","governance","Bind execution to the exact policy/compiler versions that admitted it.","Historical replay uses historical policy identity and cannot claim present-day admission."),
    HorizonSignal(2080,"h2080.crypto-retirement","cryptography","Represent algorithm deprecation and re-attestation without destroying original evidence.","Retirement blocks new issuance while preserving verification of historical receipts."),
    HorizonSignal(2080,"h2080.format-survivability","contracts","Keep a minimal deterministic interchange projection for every durable receipt generation.","Future readers must be able to distinguish unsupported schema from corrupted evidence."),
    HorizonSignal(2090,"h2090.chain-continuity","provenance","Maintain predecessor-linked re-attestation chains across all supported receipt generations.","A broken predecessor chain is a verification failure, never an implicit trust reset."),
    HorizonSignal(2090,"h2090.semantic-preservation","contracts","Require migrations to state which semantic invariants are preserved or intentionally retired.","Unknown semantic loss must fail closed rather than be accepted as compatible."),
)

def signals_for_decade(decade: int) -> tuple[HorizonSignal, ...]:
    if decade not in _VALID_DECADES:
        raise ValueError("unsupported decade")
    return tuple(signal for signal in SIGNALS if signal.decade == decade)

def horizon_manifest() -> dict[str, object]:
    ids = [signal.signal_id for signal in SIGNALS]
    if len(ids) != len(set(ids)):
        raise RuntimeError("horizon signal ids must be unique")
    return {"schema": SIGNAL_SCHEMA, "signals": [signal.as_dict() for signal in SIGNALS]}

__all__=["HorizonSignal","SIGNAL_SCHEMA","SIGNALS","horizon_manifest","signals_for_decade"]
