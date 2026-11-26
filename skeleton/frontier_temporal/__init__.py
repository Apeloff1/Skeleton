"""Deterministic temporal world memory for game-frontier observation history.

Owns the compact observation/action/camera record, the continuity and drift
evaluators, and the variable-latency present/interpolate/drop policy. It does
not replace ``skeleton.memory``, render frames, load weights, or call a model.
"""

from skeleton.frontier_temporal.evaluate import (
    Measurement,
    StoredAABB,
    evaluate_long_horizon_drift,
    evaluate_occlusion,
    evaluate_viewpoint_revisit,
    evaluate_visual_continuity,
)
from skeleton.frontier_temporal.policy import (
    TARGET_RATES,
    FramePolicyDecision,
    ObservationCursor,
    decide_frame_policy,
)
from skeleton.frontier_temporal.record import (
    EXISTING_DIGEST_FIELDS,
    GENESIS,
    CameraPose,
    EvictionSummary,
    RevisitComparison,
    TemporalMemoryError,
    TemporalRecord,
    TemporalWorldMemory,
    pose_distance,
    read_existing_digest,
)

__all__ = [
    "EXISTING_DIGEST_FIELDS",
    "GENESIS",
    "TARGET_RATES",
    "CameraPose",
    "EvictionSummary",
    "FramePolicyDecision",
    "Measurement",
    "ObservationCursor",
    "RevisitComparison",
    "StoredAABB",
    "TemporalMemoryError",
    "TemporalRecord",
    "TemporalWorldMemory",
    "decide_frame_policy",
    "evaluate_long_horizon_drift",
    "evaluate_occlusion",
    "evaluate_viewpoint_revisit",
    "evaluate_visual_continuity",
    "pose_distance",
    "read_existing_digest",
]
