"""Deterministic gameplay observation review and build handoff contracts.

This bridge prevents raw video and unclassified visual motion from being
silently promoted to user preferences or game-building instructions.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite

from .dragon_game_mechanics import (
    GameMechanicsMemory, GameObservation, GameSession,
    Mechanic, PreferenceSignal,
)
from .dragon_game_forge import (
    DragonGameForge, GameDesignConstraint, GamePrototypeSpec,
    ForgeEvaluation,
)


@dataclass(frozen=True)
class VisualEvent:
    timestamp_ms: int
    label: str
    confidence: float
    description: str
    source_frame_ms: int


@dataclass(frozen=True)
class ReviewedObservation:
    event: VisualEvent
    mechanic: Mechanic
    preference: PreferenceSignal
    user_confirmed: bool
    reviewer_note: str = ""


@dataclass(frozen=True)
class GameBuilderHandoff:
    owner: str
    prototype: GamePrototypeSpec
    evaluation: ForgeEvaluation
    taste_fingerprint: str
    review_fingerprint: str
    manifest_fingerprint: str
    requires_original_assets: bool = True


def _hash(value: object) -> str:
    return sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode()).hexdigest()


def _event(event: VisualEvent, duration_ms: int) -> None:
    if not isinstance(event.timestamp_ms, int) or not 0 <= event.timestamp_ms <= duration_ms:
        raise ValueError("event outside recording")
    if not isinstance(event.source_frame_ms, int) or not 0 <= event.source_frame_ms <= duration_ms:
        raise ValueError("invalid source frame")
    if not isinstance(event.label, str) or not 1 <= len(event.label) <= 100:
        raise ValueError("invalid visual event label")
    if not isinstance(event.description, str) or not 1 <= len(event.description) <= 500:
        raise ValueError("invalid event description")
    if not isfinite(event.confidence) or not 0 <= event.confidence <= 1:
        raise ValueError("invalid visual confidence")


def review_recording(
    store: GameMechanicsMemory, *, owner: str, game_label: str,
    duration_ms: int, observations: tuple[ReviewedObservation, ...],
    capture_consent: bool, analysis_consent: bool, authorized: bool,
) -> GameSession:
    if not authorized or not capture_consent or not analysis_consent:
        raise PermissionError("review requires explicit recording and analysis consent")
    if not observations:
        raise ValueError("no reviewed observations")
    reviewed = []
    for observation in observations:
        _event(observation.event, duration_ms)
        if observation.event.label == "unclassified_visual_change":
            raise ValueError("visual motion must be classified before review")
        if not isinstance(observation.mechanic, Mechanic):
            raise ValueError("unsupported mechanic")
        if not isinstance(observation.preference, PreferenceSignal):
            raise ValueError("unsupported preference")
        if observation.preference is not PreferenceSignal.UNKNOWN and not observation.user_confirmed:
            raise PermissionError("preference requires user confirmation")
        if not isinstance(observation.reviewer_note, str) or len(observation.reviewer_note) > 500:
            raise ValueError("invalid reviewer note")
        description = observation.event.description
        if observation.reviewer_note.strip():
            description += " | reviewer: " + observation.reviewer_note.strip()
        reviewed.append(GameObservation(
            observation.event.timestamp_ms, observation.mechanic,
            description[:store.policy.max_note_chars],
            observation.event.confidence, observation.preference,
            observation.user_confirmed,
        ))
    session = store.build_session(
        owner, game_label, duration_ms, tuple(reviewed),
        capture_consent=capture_consent, analysis_consent=analysis_consent,
    )
    store.record(session, authorized=authorized)
    return session


def prepare_game_builder_handoff(
    store: GameMechanicsMemory, forge: DragonGameForge, *,
    owner: str, constraints: GameDesignConstraint,
    authorized: bool, human_approved: bool,
    seed: int = 0,
) -> GameBuilderHandoff:
    if not authorized:
        raise PermissionError("game builder handoff requires authorization")
    if not human_approved:
        raise PermissionError("game builder requires user approval")
    taste = store.distill(owner, authorized=True)
    prototype = forge.propose(taste, constraints, authorized=True, seed=seed)
    evaluation = forge.evaluate(prototype, taste, authorized=True)
    review_fingerprint = _hash([
        owner, taste.fingerprint, prototype.candidate_id, "human-approved",
    ])
    manifest_fingerprint = _hash([
        review_fingerprint, evaluation.total,
        [m.mechanic.value for m in prototype.mechanics],
    ])
    return GameBuilderHandoff(
        owner, prototype, evaluation, taste.fingerprint,
        review_fingerprint, manifest_fingerprint,
    )
