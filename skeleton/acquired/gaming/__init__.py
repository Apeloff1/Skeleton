"""Acquired gaming primitives mined from Apeloff1 game projects."""

from skeleton.acquired.gaming.course_runtime import (
    CourseTracker,
    GateCrossing,
    Point3,
    RingGate,
    orient_ring_path,
    segment_crosses_ring,
)
from skeleton.acquired.gaming.game_building import (
    DEFAULT_GAME_BUILDING_REQUIREMENTS,
    GAME_BUILDING_SECTION,
    GameBuildIssue,
    GameBuildingSkill,
    apply_game_building_skill,
    game_building_requirements,
    validate_game_brief,
)

__all__ = [
    "CourseTracker",
    "DEFAULT_GAME_BUILDING_REQUIREMENTS",
    "GAME_BUILDING_SECTION",
    "GameBuildIssue",
    "GameBuildingSkill",
    "GateCrossing",
    "Point3",
    "RingGate",
    "apply_game_building_skill",
    "game_building_requirements",
    "orient_ring_path",
    "segment_crosses_ring",
    "validate_game_brief",
]
