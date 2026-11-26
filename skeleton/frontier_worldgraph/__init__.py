"""World-family transitions and multimodal route synthesis.

Nodes are stored in the canonical scene graph imported from
:mod:`skeleton.world`. Inverse and ethereal layers use
:class:`skeleton.jeeves.game_frontier_worlds.WorldFamily`.
"""

from skeleton.frontier_worldgraph.graph import (
    AdmittedTransition,
    ClimateBounds,
    ClimateEnvelope,
    Constraint,
    ContentAddressedEdge,
    FictionalPosition,
    MapLayer,
    TransitionRefusal,
    Traveler,
    WorldFamilyGraph,
    WorldGraphError,
    WorldNode,
    canon_digest_of,
    climate_overlaps,
    content_address,
    family_for,
)
from skeleton.frontier_worldgraph.route import Route, RouteRefusal, follow, synthesize_route

__all__ = [
    "AdmittedTransition",
    "ClimateBounds",
    "ClimateEnvelope",
    "Constraint",
    "ContentAddressedEdge",
    "FictionalPosition",
    "MapLayer",
    "Route",
    "RouteRefusal",
    "TransitionRefusal",
    "Traveler",
    "WorldFamilyGraph",
    "WorldGraphError",
    "WorldNode",
    "canon_digest_of",
    "climate_overlaps",
    "content_address",
    "family_for",
    "follow",
    "synthesize_route",
]
