from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


class PersonalLogKind(str, Enum):
    PROSPECT = "prospect"  # future intentions, goals, upcoming tasks
    EXECUTIVE_FUNCTION = "executive_function"  # step-by-step breakdown of complex problems
    INTEROCEPTION = "interoception"  # body sensations, energy, tension
    ENVIRONMENTAL_TRIGGER = "environmental_trigger"  # noise, light, weather, sensory
    COGNITIVE_BIAS = "cognitive_bias"  # automatic negative thoughts / flawed assumptions
    WORKING_MEMORY = "working_memory"  # temporary scratchpad ideas / quick math
    SOCIAL_BOUNDARY = "social_boundary"  # relational drains, boundaries, outcomes
    SKILL_ACQUISITION = "skill_acquisition"  # learning mechanics of habits/skills
    STIMULUS_RESPONSE = "stimulus_response"  # trigger → chosen reaction
    CENTRAL_SYNTHESIS = "central_synthesis"  # weekly master summary across logs
    CLIENT_LEDGER = "client_ledger"  # transcribed ambient / session notes


@dataclass
class PersonalLogEntry:
    entry_id: str
    kind: PersonalLogKind
    user_id: str
    title: str
    body: str
    tags: List[str] = field(default_factory=list)
    mood: Optional[float] = None
    intensity: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    insight_hints: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "user"  # user | transcript | system | jeeves

    @staticmethod
    def create(
        *,
        kind: PersonalLogKind,
        user_id: str,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        mood: Optional[float] = None,
        intensity: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        insight_hints: Optional[List[str]] = None,
        source: str = "user",
    ) -> "PersonalLogEntry":
        return PersonalLogEntry(
            entry_id=str(uuid.uuid4())[:12],
            kind=kind,
            user_id=user_id,
            title=title,
            body=body,
            tags=tags or [],
            mood=mood,
            intensity=intensity,
            metadata=metadata or {},
            insight_hints=insight_hints or [],
            source=source,
        )


LOG_FOCUS: Dict[PersonalLogKind, str] = {
    PersonalLogKind.PROSPECT: "Future intentions, goals, and upcoming tasks.",
    PersonalLogKind.EXECUTIVE_FUNCTION: "Step-by-step breakdown of overwhelming, complex problems.",
    PersonalLogKind.INTEROCEPTION: "Physical body sensations, energy levels, and tension points.",
    PersonalLogKind.ENVIRONMENTAL_TRIGGER: "External sensory inputs: noise, lighting, weather.",
    PersonalLogKind.COGNITIVE_BIAS: "Automatic negative thoughts or flawed logical assumptions.",
    PersonalLogKind.WORKING_MEMORY: "Messy scratchpad for temporary ideas and quick math.",
    PersonalLogKind.SOCIAL_BOUNDARY: "Relational energy drains, boundaries, communication outcomes.",
    PersonalLogKind.SKILL_ACQUISITION: "Mechanics of learning a new physical or mental habit.",
    PersonalLogKind.STIMULUS_RESPONSE: "A specific trigger and how you actively chose to react.",
    PersonalLogKind.CENTRAL_SYNTHESIS: "Weekly master summary connecting trends across all logs.",
    PersonalLogKind.CLIENT_LEDGER: "Transcribed ambient notes and session ledger entries.",
}
