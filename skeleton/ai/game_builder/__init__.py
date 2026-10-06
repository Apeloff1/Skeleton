"""Governed dual-rival game-builder runtime contracts.

The package contains deterministic control-plane primitives only. Model/provider
execution remains outside the authority boundary and must enter through governed
candidate, canon, rights, atom-lineage, and evidence contracts.
"""

from .atomizer import ArtifactAtom, AtomGraph, AtomGraphError
from .canon import CanonAssertion, CanonError, CanonLedger, CharacterKnowledge
from .contracts import (
    ArtifactIdentity,
    Candidate,
    Challenge,
    EffortMode,
    GateResult,
    PromotionReceipt,
    Rival,
    Stage,
    canonical_digest,
)
from .dual_rival_forge import DualRivalForge, ForgeStateError
from .rights import (
    IncorporationDecision,
    RightsError,
    RightsLedger,
    RightsState,
    SimilarityFinding,
    SimilarityRisk,
    SourceRecord,
    UseKind,
)

__all__ = [
    "ArtifactAtom",
    "ArtifactIdentity",
    "AtomGraph",
    "AtomGraphError",
    "Candidate",
    "CanonAssertion",
    "CanonError",
    "CanonLedger",
    "Challenge",
    "CharacterKnowledge",
    "DualRivalForge",
    "EffortMode",
    "ForgeStateError",
    "GateResult",
    "IncorporationDecision",
    "PromotionReceipt",
    "RightsError",
    "RightsLedger",
    "RightsState",
    "Rival",
    "SimilarityFinding",
    "SimilarityRisk",
    "SourceRecord",
    "Stage",
    "UseKind",
    "canonical_digest",
]
