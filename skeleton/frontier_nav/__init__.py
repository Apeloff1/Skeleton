"""GF-H: authoritative per-frame GPS/navigation hooks and NPC route grounding.

Extend-only package. Callers inject ports (clock, signature verifier, era
catalogue) so Internal Systems / Backend modules plug in through adapters.
"""

from skeleton.frontier_nav.gps import (
    FICTIONAL_LAYER_KINDS,
    MINIMAP_ZOOMS,
    FictionalMapLayer,
    FictionalPortal,
    FrameFix,
    FrameGPSHub,
    FramePositionSource,
    FrameProof,
    GPSRejected,
    MinimapCamera,
    NavUpdate,
    NavigationCursor,
    PositionFix,
    TypedFrame,
    clamp_minimap_camera,
    follow_portal,
    jump_minimap_layer,
    minimap_viewport,
    opening_camera,
    pan_minimap,
    validate_fictional_portals,
    zoom_minimap,
)
from skeleton.frontier_nav.survey_approval import (
    FICTIONAL_DATUM,
    SurveyAuthorityError,
    SurveyBook,
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
    "FICTIONAL_DATUM",
    "FICTIONAL_LAYER_KINDS",
    "FictionalMapLayer",
    "FictionalPortal",
    "FrameFix",
    "FrameGPSHub",
    "FramePositionSource",
    "FrameProof",
    "GPSRejected",
    "GroundedPlan",
    "GroundingRejected",
    "MINIMAP_ZOOMS",
    "MinimapCamera",
    "NavUpdate",
    "NavigationCursor",
    "PositionFix",
    "RouteGrounder",
    "SurveyAuthorityError",
    "SurveyBook",
    "TypedFrame",
    "clamp_minimap_camera",
    "follow_portal",
    "hmac_verifier",
    "jump_minimap_layer",
    "minimap_viewport",
    "opening_camera",
    "pan_minimap",
    "validate_fictional_portals",
    "zoom_minimap",
]
