"""GF-H: authoritative per-frame GPS/navigation hooks and NPC route grounding.

Extend-only package. Callers inject ports (clock, signature verifier, era
catalogue) so Internal Systems / Backend modules plug in through adapters.
"""

from skeleton.frontier_nav.gps import (
    FrameGPSHub,
    FrameProof,
    GPSRejected,
    NavUpdate,
    PositionFix,
)
from skeleton.frontier_nav.route_grounding import (
    ApprovedRoute,
    DesignNote,
    GroundedPlan,
    GroundingRejected,
    RouteGrounder,
    hmac_verifier,
)

__all__ = [
    "ApprovedRoute",
    "DesignNote",
    "FrameGPSHub",
    "FrameProof",
    "GPSRejected",
    "GroundedPlan",
    "GroundingRejected",
    "NavUpdate",
    "PositionFix",
    "RouteGrounder",
    "hmac_verifier",
]
