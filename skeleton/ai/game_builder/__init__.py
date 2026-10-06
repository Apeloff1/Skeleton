"""Governed dual-rival game-builder runtime contracts.

This package contains deterministic control-plane primitives only. Model/provider
execution remains outside the authority boundary and must enter through governed
candidate/evidence contracts.
"""

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

__all__ = [
    "ArtifactIdentity",
    "Candidate",
    "Challenge",
    "DualRivalForge",
    "EffortMode",
    "ForgeStateError",
    "GateResult",
    "PromotionReceipt",
    "Rival",
    "Stage",
    "canonical_digest",
]
