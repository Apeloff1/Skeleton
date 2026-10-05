from __future__ import annotations
"""
Authoritative trigger definitions for GameForge personal stack.

Each trigger: WHEN (conditions) → THEN (actions) → WITH (guards).
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class TriggerId(str, Enum):
    # Ingest
    T_TRANSCRIPT_SEGMENT = "transcript_segment"
    T_USER_LOG_WRITE = "user_log_write"
    T_COMMAND_PHRASE = "command_phrase"

    # Time
    T_DAY_START = "day_start"
    T_MIDNIGHT_CONSOLIDATION = "midnight_consolidation"
    T_YEAR_FILL_CHECK = "year_fill_check"

    # Body / affect
    T_SLEEP_REPORTED = "sleep_reported"
    T_AFFECT_REFRESH = "affect_refresh"
    T_PAIN_SPIKE = "pain_spike"

    # Calendar / env
    T_LOCATION_CHANGE = "location_change"
    T_WEATHER_REFRESH = "weather_refresh"
    T_SCHEDULE_ADD_REQUEST = "schedule_add_request"
    T_PROGRESS_UPDATE = "progress_update"

    # Social / place
    T_GUEST_SIGNAL = "guest_signal"
    T_BUILDING_SIGNAL = "building_signal"

    # Derived
    T_SALIENCE_KEEP = "salience_keep"
    T_HOMEOSTASIS_CRITICAL = "homeostasis_critical"
    T_PREDICTIVE_HIGH_RISK = "predictive_high_risk"
    T_PLASTICITY_MATCH = "plasticity_match"
    T_REWARD_EVENT = "reward_event"


@dataclass
class TriggerSpec:
    id: TriggerId
    description: str
    when: str
    then: List[str]
    guards: List[str] = field(default_factory=list)
    priority: int = 50  # higher = earlier

    def to_dict(self) -> dict:
        return {
            "id": self.id.value,
            "description": self.description,
            "when": self.when,
            "then": self.then,
            "guards": self.guards,
            "priority": self.priority,
        }


# --- Canonical matrix -------------------------------------------------------

TRIGGER_SPECS: List[TriggerSpec] = [
    TriggerSpec(
        TriggerId.T_TRANSCRIPT_SEGMENT,
        "Always-on or session transcript chunk arrived",
        "New text segment from STT",
        [
            "salience.score(segment)",
            "if keep and category in {insight,health,command,emotional}: client_ledger.add",
            "if keep and importance>=0.75: fisherman.catch(today)",
            "if guest_patterns: guest_log.note_guest",
            "if command: route_command",
        ],
        guards=["recording.consent", "salience.threshold"],
        priority=90,
    ),
    TriggerSpec(
        TriggerId.T_SALIENCE_KEEP,
        "Segment passed relevance filter",
        "salience.score >= threshold",
        [
            "persist_to_client_ledger",
            "maybe_fisherman_catch",
            "insight_engine.extract_hints",
            "health_empathy.maybe_nudge",
        ],
        priority=85,
    ),
    TriggerSpec(
        TriggerId.T_DAY_START,
        "Local day boundary / first Jeeves open",
        "calendar.date changed or explicit day_start",
        [
            "calendar.get_day(enrich=True)",
            "affect.simulate_from_weather",
            "neuro.daily_control_plane(...)",
            "plasticity.intervene(weather, noise, valence)",
            "predictive.forecast(...)",
            "jeeves.context.refresh",
        ],
        priority=80,
    ),
    TriggerSpec(
        TriggerId.T_SLEEP_REPORTED,
        "Sleep hours known for last night",
        "user or wearable reports sleep_hours",
        [
            "neuromod.compute(sleep_hours)",
            "if sleep_hours < 5.5: capacity_scale=0.5",
            "homeostasis.evaluate",
            "predictive.observe+forecast",
        ],
        priority=75,
    ),
    TriggerSpec(
        TriggerId.T_AFFECT_REFRESH,
        "Weather/noise/temp produced new daily affect",
        "weather_refresh completed",
        [
            "neuromod.blend(affect_energy, valence)",
            "plasticity.observe_day",
            "jeeves.tone.apply(affect.jeeves_guidance)",
        ],
        priority=70,
    ),
    TriggerSpec(
        TriggerId.T_SCHEDULE_ADD_REQUEST,
        "User or agent tries to add a schedule item",
        "POST schedule or internal add_schedule",
        [
            "homeostasis.assert_can_schedule",
            "if locked: reject",
            "if predictive.risk high|critical: warn + soft-cap",
            "if over neuromod.max_tasks: defer suggestion",
            "else: calendar.add_schedule + link decade logs if tagged",
        ],
        guards=["not homeostasis.schedule_locked"],
        priority=95,
    ),
    TriggerSpec(
        TriggerId.T_PROGRESS_UPDATE,
        "Project percent updated for a day",
        "set_project_progress",
        [
            "neuromod.register_reward if delta>0",
            "plasticity.observe_day(progress_delta)",
            "if percent>=100: fisherman.catch milestone",
        ],
        priority=60,
    ),
    TriggerSpec(
        TriggerId.T_PAIN_SPIKE,
        "Patient/somatic pain elevated",
        "pain_level >= 0.6 or interoception tags pain",
        [
            "homeostasis.evaluate(pain)",
            "predictive.forecast",
            "if critical: lock schedule",
            "jeeves.health_empathy.supportive_tone",
        ],
        priority=92,
    ),
    TriggerSpec(
        TriggerId.T_HOMEOSTASIS_CRITICAL,
        "Equilibrium below lock threshold",
        "homeostasis.status == critical",
        [
            "schedule_locked=True",
            "reject new tasks",
            "jeeves.directive: recover baseline",
        ],
        priority=100,
    ),
    TriggerSpec(
        TriggerId.T_PREDICTIVE_HIGH_RISK,
        "Forecasted collapse within horizon",
        "predictive.risk_level in {high, critical}",
        [
            "preemptive capacity cut",
            "suggest recovery block on calendar",
            "plasticity prefer low_cognition",
        ],
        priority=88,
    ),
    TriggerSpec(
        TriggerId.T_PLASTICITY_MATCH,
        "Historical failure pattern matches today",
        "plasticity.intervene.active",
        [
            "jeeves.message = intervention.message",
            "task_mode = low_cognition",
            "reduce max_tasks by 25%",
        ],
        priority=72,
    ),
    TriggerSpec(
        TriggerId.T_MIDNIGHT_CONSOLIDATION,
        "End of local day consolidation window",
        "clock in consolidation window OR explicit run",
        [
            "gather transcript segments of day",
            "salience.filter_batch",
            "sleep_consolidation.consolidate → decade_essence",
            "top salient → fisherman.catch",
            "year_fill_check",
        ],
        priority=65,
    ),
    TriggerSpec(
        TriggerId.T_YEAR_FILL_CHECK,
        "After consolidation or manual",
        "filled_day_ratio or schedule_items past threshold",
        [
            "era_log.distill_year(calendar, decade_hub)",
            "if distilled: jeeves note new era link",
        ],
        priority=40,
    ),
    TriggerSpec(
        TriggerId.T_LOCATION_CHANGE,
        "User country/city changed",
        "POST /calendar/location",
        [
            "calendar.set_location",
            "refresh occasions/holidays",
            "weather re-seed for city",
            "affect refresh",
        ],
        priority=55,
    ),
    TriggerSpec(
        TriggerId.T_GUEST_SIGNAL,
        "Transcript or user notes a non-user person",
        "guest entity detected or POST /decade/guest",
        ["guest_log.note_guest", "link calendar_ref=today"],
        priority=50,
    ),
    TriggerSpec(
        TriggerId.T_BUILDING_SIGNAL,
        "Place/environment change noted",
        "POST /decade/building or tagged log",
        ["building_log.note_building", "link calendar_ref=today"],
        priority=50,
    ),
    TriggerSpec(
        TriggerId.T_REWARD_EVENT,
        "Win / milestone / positive reinforcement",
        "progress up, accomplishment journal, explicit reward",
        [
            "neuromod.register_reward",
            "optional retrospect diary",
            "fisherman.catch if high importance",
        ],
        priority=58,
    ),
]


def trigger_matrix() -> List[dict]:
    return [s.to_dict() for s in sorted(TRIGGER_SPECS, key=lambda x: -x.priority)]


def specs_by_id() -> Dict[str, TriggerSpec]:
    return {s.id.value: s for s in TRIGGER_SPECS}
