"""Baby dragon companion orchestration: consented research and memory animation.

Pure deterministic state machine; no browser/network calls. Frontends can
render the same transitions on desktop, mobile, and accessibility surfaces.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from math import isfinite
import json


class DragonMood(str, Enum):
    SLEEPY = "sleepy"
    CURIOUS = "curious"
    EXCITED = "excited"
    FOCUSED = "focused"
    PROUD = "proud"
    WORRIED = "worried"


class DragonPhase(str, Enum):
    NESTING = "nesting"
    LISTENING = "listening"
    SEARCHING = "searching"
    ACQUIRING = "acquiring"
    BURNING = "burning"
    DISTILLING = "distilling"
    VERIFYING = "verifying"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEMBERING = "remembering"
    RESTING = "resting"
    ERROR = "error"


class DragonEvent(str, Enum):
    WAKE = "wake"
    TALK = "talk"
    START_RESEARCH = "start_research"
    DISCOVER = "discover"
    CAPTURE = "capture"
    START_DISTILL = "start_distill"
    DISTILLED = "distilled"
    VERIFIED = "verified"
    REQUEST_APPROVAL = "request_approval"
    APPROVED = "approved"
    STORED = "stored"
    REST = "rest"
    FAIL = "fail"
    RESET = "reset"


@dataclass(frozen=True)
class DragonCompanionPolicy:
    max_topic_chars: int = 240
    max_progress_events: int = 10000
    require_research_consent: bool = True
    require_human_memory_approval: bool = True


@dataclass(frozen=True)
class DragonCompanionState:
    owner: str
    phase: DragonPhase = DragonPhase.NESTING
    mood: DragonMood = DragonMood.SLEEPY
    topic: str = ""
    progress: float = 0.0
    has_eggshell_hat: bool = True
    wears_glasses: bool = False
    taped_glasses_bridge: bool = False
    flame_active: bool = False
    memory_sparks: int = 0
    approved: bool = False
    consented: bool = False
    events: int = 0
    last_error: str = ""
    fingerprint: str = ""


_ALLOWED: dict[DragonPhase, dict[DragonEvent, DragonPhase]] = {
    DragonPhase.NESTING: {
        DragonEvent.WAKE: DragonPhase.LISTENING,
        DragonEvent.TALK: DragonPhase.LISTENING,
    },
    DragonPhase.LISTENING: {
        DragonEvent.TALK: DragonPhase.LISTENING,
        DragonEvent.START_RESEARCH: DragonPhase.SEARCHING,
        DragonEvent.REST: DragonPhase.RESTING,
    },
    DragonPhase.SEARCHING: {
        DragonEvent.DISCOVER: DragonPhase.ACQUIRING,
        DragonEvent.REST: DragonPhase.RESTING,
    },
    DragonPhase.ACQUIRING: {
        DragonEvent.CAPTURE: DragonPhase.BURNING,
    },
    DragonPhase.BURNING: {
        DragonEvent.START_DISTILL: DragonPhase.DISTILLING,
    },
    DragonPhase.DISTILLING: {
        DragonEvent.DISTILLED: DragonPhase.VERIFYING,
    },
    DragonPhase.VERIFYING: {
        DragonEvent.VERIFIED: DragonPhase.AWAITING_APPROVAL,
        DragonEvent.REQUEST_APPROVAL: DragonPhase.AWAITING_APPROVAL,
    },
    DragonPhase.AWAITING_APPROVAL: {
        DragonEvent.APPROVED: DragonPhase.REMEMBERING,
    },
    DragonPhase.REMEMBERING: {
        DragonEvent.STORED: DragonPhase.LISTENING,
    },
    DragonPhase.RESTING: {
        DragonEvent.WAKE: DragonPhase.LISTENING,
    },
    DragonPhase.ERROR: {
        DragonEvent.RESET: DragonPhase.LISTENING,
    },
}


def new_companion(owner: str) -> DragonCompanionState:
    if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
        raise ValueError("invalid companion owner")
    return DragonCompanionState(owner=owner)


def transition(
    state: DragonCompanionState,
    event: DragonEvent,
    *, topic: str = "", consent: bool = False,
    human_approved: bool = False,
    progress: float | None = None,
    error: str = "",
    policy: DragonCompanionPolicy = DragonCompanionPolicy(),
) -> DragonCompanionState:
    if not isinstance(state, DragonCompanionState):
        raise ValueError("invalid companion state")
    if not isinstance(event, DragonEvent):
        raise ValueError("invalid companion event")
    if state.events >= policy.max_progress_events:
        raise ValueError("companion event budget exceeded")
    if event is DragonEvent.FAIL:
        phase = DragonPhase.ERROR
    else:
        phase = _ALLOWED.get(state.phase, {}).get(event)
        if phase is None:
            raise ValueError(f"invalid companion transition: {state.phase.value}/{event.value}")
    if event is DragonEvent.START_RESEARCH:
        if policy.require_research_consent and not consent:
            raise PermissionError("research requires explicit consent")
        if not isinstance(topic, str) or not 2 <= len(topic.strip()) <= policy.max_topic_chars:
            raise ValueError("invalid research topic")
    if event is DragonEvent.APPROVED and policy.require_human_memory_approval:
        if not human_approved:
            raise PermissionError("memory promotion requires human approval")
    if progress is not None and (
        not isinstance(progress, (int, float))
        or not isfinite(progress) or not 0 <= progress <= 1
    ):
        raise ValueError("invalid companion progress")
    if progress is not None and progress < state.progress and event not in (
        DragonEvent.START_RESEARCH, DragonEvent.RESET,
    ):
        raise ValueError("progress cannot move backwards")
    if event is DragonEvent.STORED and not state.approved:
        raise PermissionError("unapproved knowledge cannot be remembered")
    mood = {
        DragonPhase.NESTING: DragonMood.SLEEPY,
        DragonPhase.LISTENING: DragonMood.CURIOUS,
        DragonPhase.SEARCHING: DragonMood.EXCITED,
        DragonPhase.ACQUIRING: DragonMood.EXCITED,
        DragonPhase.BURNING: DragonMood.FOCUSED,
        DragonPhase.DISTILLING: DragonMood.FOCUSED,
        DragonPhase.VERIFYING: DragonMood.FOCUSED,
        DragonPhase.AWAITING_APPROVAL: DragonMood.WORRIED,
        DragonPhase.REMEMBERING: DragonMood.PROUD,
        DragonPhase.RESTING: DragonMood.SLEEPY,
        DragonPhase.ERROR: DragonMood.WORRIED,
    }[phase]
    glasses = phase in (
        DragonPhase.DISTILLING, DragonPhase.VERIFYING,
        DragonPhase.AWAITING_APPROVAL,
    )
    flame = phase is DragonPhase.BURNING
    approved = (state.approved or human_approved) if phase is DragonPhase.REMEMBERING else False
    next_progress = (
        0.0 if event in (DragonEvent.START_RESEARCH, DragonEvent.RESET)
        else 1.0 if event is DragonEvent.STORED
        else state.progress if progress is None else float(progress)
    )
    payload = [
        state.fingerprint, event.value, phase.value, topic or state.topic,
        next_progress, approved, state.events + 1,
    ]
    fingerprint = sha256(json.dumps(
        payload, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()
    return replace(
        state, phase=phase, mood=mood,
        topic=topic.strip() if event is DragonEvent.START_RESEARCH else state.topic,
        progress=next_progress,
        wears_glasses=glasses,
        taped_glasses_bridge=glasses,
        flame_active=flame,
        memory_sparks=min(64, state.memory_sparks + (8 if flame else 0)),
        approved=approved,
        consented=consent if event is DragonEvent.START_RESEARCH else state.consented,
        events=state.events + 1,
        last_error=error[:500] if event is DragonEvent.FAIL else "",
        fingerprint=fingerprint,
    )


def animation_frame(state: DragonCompanionState) -> dict:
    """Serializable visual contract for UI animation and reduced-motion mode."""
    return {
        "phase": state.phase.value,
        "mood": state.mood.value,
        "egg": {"half_hatched": True, "hat": state.has_eggshell_hat},
        "glasses": {
            "visible": state.wears_glasses,
            "white_tape": state.taped_glasses_bridge,
        },
        "fire": {"visible": state.flame_active, "sparks": state.memory_sparks},
        "progress": state.progress,
        "topic": state.topic,
        "accessible_status": {
            DragonPhase.BURNING: "The dragon is transforming collected material.",
            DragonPhase.DISTILLING: "The dragon is distilling evidence.",
            DragonPhase.VERIFYING: "The dragon is checking source reliability.",
            DragonPhase.AWAITING_APPROVAL: "The dragon needs your approval.",
            DragonPhase.REMEMBERING: "The dragon is saving approved knowledge.",
        }.get(state.phase, f"Dragon is {state.phase.value}."),
    }
