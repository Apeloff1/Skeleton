"""Acquired gaming primitives mined from Apeloff1 game projects."""

from skeleton.acquired.gaming.course_runtime import (
    CourseTracker,
    GateCrossing,
    Point3,
    RingGate,
    orient_ring_path,
    segment_crosses_ring,
)
from skeleton.acquired.gaming.knowledge import (
    GameKnowledgeBase,
    GameReference,
    ScoredGameReference,
    build_game_knowledge_context,
)

__all__ = [
    "CourseTracker",
    "GameKnowledgeBase",
    "GameReference",
    "GateCrossing",
    "Point3",
    "RingGate",
    "ScoredGameReference",
    "build_game_knowledge_context",
    "orient_ring_path",
    "segment_crosses_ring",
]
