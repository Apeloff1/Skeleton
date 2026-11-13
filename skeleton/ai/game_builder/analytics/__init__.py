"""Gameplay analytics for generated games (data layer only).

Typed events -> privacy filter (sampling, opt-out, pseudonymous ids, no PII)
-> sessions, funnels, retention, per-level/encounter drop-off and a
``DifficultyHeatmap`` keyed by the plan's own level and encounter ids.
No platform telemetry, routes, dashboards or network calls. Stdlib only.
"""
from .events import EventType, EventError, GameplayEvent
from .metrics import (
    DifficultyCell, DifficultyHeatmap, Funnel, FunnelResult, Session, StageStats, build_sessions,
    difficulty_heatmap, retention, stage_stats,
)
from .privacy import Collector, PrivacyPolicy

__all__ = [
    "EventType", "EventError", "GameplayEvent", "DifficultyCell", "DifficultyHeatmap", "Funnel",
    "FunnelResult", "Session", "StageStats", "build_sessions", "difficulty_heatmap", "retention",
    "stage_stats", "Collector", "PrivacyPolicy",
]
