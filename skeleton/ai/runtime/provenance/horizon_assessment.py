"""Evaluate native replay contracts against decade-horizon engineering signals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .horizon_signals import SIGNALS

@dataclass(frozen=True, slots=True)
class SignalAssessment:
    signal_id: str
    state: str
    evidence: tuple[str, ...]
    gap: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"satisfied", "partial", "planned"}:
            raise ValueError("invalid signal assessment state")
        if self.state == "satisfied" and self.gap is not None:
            raise ValueError("satisfied signal cannot declare a gap")
        if self.state != "satisfied" and not self.gap:
            raise ValueError("incomplete signal must declare a gap")

# Static architectural assessment. Evidence values are stable contract symbols,
# not claims that a particular CI run has executed.
_ASSESSMENTS: Final[dict[str, SignalAssessment]] = {
    "h2020.content-addressing": SignalAssessment("h2020.content-addressing","satisfied",("ReplayReceipt.request_digest","ReplayReceipt.output_digest","ReplayReceipt.model_digest","ReplayReceipt.tokenizer_digest")),
    "h2020.replay": SignalAssessment("h2020.replay","satisfied",("ReplayReceipt","NativeLLMRuntime.replay")),
    "h2030.algorithm-agility": SignalAssessment("h2030.algorithm-agility","partial",("sha256-shaped canonical digests",),"durable receipts do not yet carry an explicit digest algorithm identifier"),
    "h2030.multi-runtime": SignalAssessment("h2030.multi-runtime","partial",("ReplayReceipt.device_digest","ReplayReceipt.request_digest"),"semantic request identity and execution identity need a first-class cross-runtime receipt"),
    "h2040.provenance-portability": SignalAssessment("h2040.provenance-portability","partial",("ReplayReceipt.to_dict","ContextEnvelope.audit_dict"),"portable verifier package/schema registry is not yet explicit"),
    "h2040.lineage-graph": SignalAssessment("h2040.lineage-graph","satisfied",("ContextSegment.derived_from","ContextEnvelope.source_snapshot")),
    "h2050.archive-verification": SignalAssessment("h2050.archive-verification","partial",("content_digest","source_snapshot"),"archival retention/export contract is not bound to replay receipts"),
    "h2050.receipt-upconversion": SignalAssessment("h2050.receipt-upconversion","planned",(),"receipt migration and predecessor-digest contract is not implemented"),
    "h2060.heterogeneous-proof": SignalAssessment("h2060.heterogeneous-proof","planned",(),"receipt supports one digest lineage and no proof-set abstraction"),
    "h2060.offline-verification": SignalAssessment("h2060.offline-verification","partial",("ReplayReceipt.to_dict","deterministic digest_json"),"standalone verifier API is not yet exposed"),
    "h2070.identity-continuity": SignalAssessment("h2070.identity-continuity","partial",("model_digest","tokenizer_digest","architecture_digest","device_digest"),"semantic artifact identity is not separately versioned from implementation identity"),
    "h2070.policy-history": SignalAssessment("h2070.policy-history","partial",("ContextEnvelope.compiler_version","context_digest"),"runtime replay receipt does not directly bind admission-policy identity"),
    "h2080.crypto-retirement": SignalAssessment("h2080.crypto-retirement","planned",(),"algorithm registry and issuance/verification lifecycle are not implemented"),
    "h2080.format-survivability": SignalAssessment("h2080.format-survivability","partial",("REPLAY_SCHEMA","ReplayReceipt.to_dict"),"no minimal long-term interchange profile is declared"),
    "h2090.chain-continuity": SignalAssessment("h2090.chain-continuity","planned",(),"re-attestation predecessor chain is not implemented"),
    "h2090.semantic-preservation": SignalAssessment("h2090.semantic-preservation","planned",(),"migration invariant declarations are not implemented"),
}

def assess_horizon_signals() -> tuple[SignalAssessment, ...]:
    expected = {signal.signal_id for signal in SIGNALS}
    actual = set(_ASSESSMENTS)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(f"horizon assessment mismatch missing={missing} extra={extra}")
    return tuple(_ASSESSMENTS[signal.signal_id] for signal in SIGNALS)

def horizon_gap_manifest() -> dict[str, object]:
    rows = assess_horizon_signals()
    counts = {state: sum(row.state == state for row in rows) for state in ("satisfied","partial","planned")}
    return {
        "schema": "skeleton.ai.horizon-gap-assessment.v1",
        "counts": counts,
        "assessments": [
            {"signal_id": row.signal_id,"state": row.state,"evidence": list(row.evidence),"gap": row.gap}
            for row in rows
        ],
    }

__all__=["SignalAssessment","assess_horizon_signals","horizon_gap_manifest"]
