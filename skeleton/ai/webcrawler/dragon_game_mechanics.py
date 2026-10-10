"""Consent-scoped game session observations and mechanics-to-taste distillation.

Screen recordings are captured by a separate, user-initiated client. This
module never records a screen, extracts hidden user behavior, or claims that
visual gameplay alone proves a mechanic. A vision model or user supplies
explicit, timestamped observations with confidence and provenance; this
module validates, aggregates and turns them into *provisional* design
preferences for a game builder. No raw video is retained here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
import json
import sqlite3


class Mechanic(str, Enum):
    MOVEMENT = "movement"
    CAMERA = "camera"
    COMBAT = "combat"
    PUZZLE = "puzzle"
    EXPLORATION = "exploration"
    CRAFTING = "crafting"
    BUILDING = "building"
    DIALOGUE = "dialogue"
    STEALTH = "stealth"
    PLATFORMING = "platforming"
    RESOURCE_MANAGEMENT = "resource_management"
    PROGRESSION = "progression"
    COOPERATION = "cooperation"
    PHYSICS = "physics"
    LEVEL_DESIGN = "level_design"
    USER_INTERFACE = "user_interface"


class PreferenceSignal(str, Enum):
    ENJOYED = "enjoyed"
    DISLIKED = "disliked"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CapturePolicy:
    max_session_seconds: int = 1800
    max_observations: int = 2000
    max_note_chars: int = 500
    max_sessions_per_owner: int = 1000
    min_confidence: float = 0.5


@dataclass(frozen=True)
class GameObservation:
    timestamp_ms: int
    mechanic: Mechanic
    description: str
    confidence: float
    preference: PreferenceSignal = PreferenceSignal.UNKNOWN
    user_confirmed: bool = False


@dataclass(frozen=True)
class GameSession:
    session_id: str
    owner: str
    game_label: str
    duration_ms: int
    observations: tuple[GameObservation, ...]
    capture_consent: bool
    analysis_consent: bool
    raw_video_retained: bool = False


@dataclass(frozen=True)
class MechanicInsight:
    mechanic: Mechanic
    observation_count: int
    supporting_sessions: int
    preference_score: float
    confidence: float
    examples: tuple[str, ...]
    user_confirmed: bool


@dataclass(frozen=True)
class GameTasteProfile:
    owner: str
    insights: tuple[MechanicInsight, ...]
    design_directives: tuple[str, ...]
    review_required: bool
    fingerprint: str


class GameMechanicsMemory:
    def __init__(self, db: sqlite3.Connection,
                 *, policy: CapturePolicy = CapturePolicy()):
        if not isinstance(policy, CapturePolicy):
            raise ValueError("CapturePolicy required")
        if type(policy.max_session_seconds) is not int or not 1 <= policy.max_session_seconds <= 14400:
            raise ValueError("invalid capture duration budget")
        if type(policy.max_observations) is not int or not 1 <= policy.max_observations <= 100000:
            raise ValueError("invalid observation budget")
        if type(policy.max_note_chars) is not int or not 1 <= policy.max_note_chars <= 5000:
            raise ValueError("invalid note budget")
        if type(policy.max_sessions_per_owner) is not int or not 1 <= policy.max_sessions_per_owner <= 100000:
            raise ValueError("invalid session capacity")
        if (type(policy.min_confidence) not in (int, float) or not 0 <= policy.min_confidence <= 1
                or not isfinite(policy.min_confidence)):
            raise ValueError("invalid confidence threshold")
        self.db = db
        self.policy = policy
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_game_sessions (
                owner TEXT NOT NULL,
                session_id TEXT NOT NULL,
                game_label TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                observations_json TEXT NOT NULL,
                PRIMARY KEY(owner, session_id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS dragon_game_session_owner
            ON dragon_game_sessions(owner, session_id)
        """)
        db.commit()

    @staticmethod
    def _owner(owner: str) -> str:
        if (not isinstance(owner, str) or not 1 <= len(owner) <= 128
                or owner != owner.strip() or not owner.isprintable()
                or len(owner.encode("utf-8")) > 256):
            raise ValueError("invalid owner")
        return owner

    def record(self, session: GameSession, *, authorized: bool) -> str:
        if (not isinstance(session, GameSession) or authorized is not True
                or session.capture_consent is not True or session.analysis_consent is not True):
            raise PermissionError("game observation storage requires explicit consent")
        owner = self._owner(session.owner)
        if session.raw_video_retained is not False:
            raise ValueError("raw recording retention requires a separate storage policy")
        if (not isinstance(session.game_label, str) or not 1 <= len(session.game_label) <= 200
                or not session.game_label.isprintable()
                or len(session.game_label.encode("utf-8")) > 600):
            raise ValueError("invalid game label")
        if type(session.duration_ms) is not int or not 0 < session.duration_ms <= self.policy.max_session_seconds * 1000:
            raise ValueError("invalid session duration")
        if (not isinstance(session.observations, tuple)
                or not 1 <= len(session.observations) <= self.policy.max_observations
                or any(not isinstance(obs, GameObservation) for obs in session.observations)):
            raise ValueError("invalid observation collection")
        rows = []
        previous_timestamp = -1
        for obs in session.observations:
            if type(obs.timestamp_ms) is not int or not 0 <= obs.timestamp_ms <= session.duration_ms:
                raise ValueError("observation outside recording")
            if obs.timestamp_ms < previous_timestamp:
                raise ValueError("observation timestamps must be in recording order")
            previous_timestamp = obs.timestamp_ms
            if not isinstance(obs.mechanic, Mechanic) or not isinstance(obs.preference, PreferenceSignal):
                raise ValueError("unknown game mechanic or preference")
            if not isinstance(obs.description, str) or not 1 <= len(obs.description) <= self.policy.max_note_chars:
                raise ValueError("invalid observation note")
            if (type(obs.confidence) not in (int, float)
                    or not 0 <= obs.confidence <= 1
                    or not isfinite(obs.confidence)):
                raise ValueError("invalid observation confidence")
            if type(obs.user_confirmed) is not bool:
                raise ValueError("observation confirmation must be boolean")
            if obs.preference is not PreferenceSignal.UNKNOWN and obs.user_confirmed is not True:
                raise PermissionError("taste signals require explicit user confirmation")
            rows.append([
                obs.timestamp_ms, obs.mechanic.value, obs.description,
                obs.confidence, obs.preference.value, obs.user_confirmed,
            ])
        payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
        expected = sha256(json.dumps(
            [owner, session.game_label, session.duration_ms, rows],
            separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        if session.session_id != expected:
            raise ValueError("session identifier does not match observations")
        with self.db:
            count = self.db.execute(
                "SELECT COUNT(*) FROM dragon_game_sessions WHERE owner=?",
                (owner,),
            ).fetchone()[0]
            existing = self.db.execute(
                "SELECT 1 FROM dragon_game_sessions WHERE owner=? AND session_id=?",
                (owner, session.session_id),
            ).fetchone()
            if not existing and count >= self.policy.max_sessions_per_owner:
                raise ValueError("session capacity exceeded")
            self.db.execute("""
                INSERT OR IGNORE INTO dragon_game_sessions
                (owner, session_id, game_label, duration_ms, observations_json)
                VALUES (?, ?, ?, ?, ?)
            """, (owner, session.session_id, session.game_label, session.duration_ms, payload))
        return expected

    @staticmethod
    def build_session(owner: str, game_label: str, duration_ms: int,
                      observations: tuple[GameObservation, ...],
                      *, capture_consent: bool, analysis_consent: bool) -> GameSession:
        rows = [[o.timestamp_ms, o.mechanic.value, o.description, o.confidence,
                 o.preference.value, o.user_confirmed] for o in observations]
        session_id = sha256(json.dumps(
            [owner, game_label, duration_ms, rows],
            separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        return GameSession(session_id, owner, game_label, duration_ms,
                           observations, capture_consent, analysis_consent)

    def sessions(self, owner: str, *, authorized: bool, limit: int = 100
                 ) -> tuple[GameSession, ...]:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("game history requires authorization")
        if not 1 <= limit <= 1000:
            raise ValueError("invalid history limit")
        rows = self.db.execute("""
            SELECT session_id, game_label, duration_ms, observations_json
            FROM dragon_game_sessions WHERE owner=?
            ORDER BY session_id LIMIT ?
        """, (owner, limit)).fetchall()
        sessions = []
        for session_id, label, duration, raw in rows:
            observations = tuple(
                GameObservation(t, Mechanic(m), d, c, PreferenceSignal(p), u)
                for t, m, d, c, p, u in json.loads(raw)
            )
            sessions.append(GameSession(
                session_id, owner, label, duration, observations, True, True,
            ))
        return tuple(sessions)

    def distill(self, owner: str, *, authorized: bool,
                limit: int = 100) -> GameTasteProfile:
        sessions = self.sessions(owner, authorized=authorized, limit=limit)
        groups: dict[Mechanic, list[tuple[GameObservation, str]]] = {}
        for session in sessions:
            for observation in session.observations:
                if observation.confidence >= self.policy.min_confidence:
                    groups.setdefault(observation.mechanic, []).append(
                        (observation, session.session_id)
                    )
        insights = []
        directives = []
        for mechanic in sorted(groups, key=lambda item: item.value):
            observations = groups[mechanic]
            confirmed = [
                obs for obs, _ in observations
                if obs.user_confirmed and obs.preference in (
                    PreferenceSignal.ENJOYED, PreferenceSignal.DISLIKED,
                )
            ]
            total = sum(obs.confidence for obs in confirmed)
            score = (
                sum(obs.confidence * (
                    1 if obs.preference is PreferenceSignal.ENJOYED else -1
                ) for obs in confirmed) / total if total else 0.0
            )
            confidence = sum(obs.confidence for obs, _ in observations) / len(observations)
            examples = tuple(sorted({
                obs.description for obs, _ in observations
            }))[:5]
            insights.append(MechanicInsight(
                mechanic, len(observations),
                len({sid for _, sid in observations}),
                round(score, 4), round(confidence, 4), examples,
                bool(confirmed),
            ))
            if confirmed and score >= 0.25:
                directives.append(
                    f"Explore {mechanic.value.replace('_', ' ')} mechanics; "
                    "validate the design with the user before implementation."
                )
            elif confirmed and score <= -0.25:
                directives.append(
                    f"Offer alternatives to {mechanic.value.replace('_', ' ')} "
                    "mechanics; confirm tradeoffs with the user."
                )
        fingerprint = sha256(json.dumps(
            [owner, [(x.mechanic.value, x.observation_count,
                      x.preference_score, x.confidence) for x in insights]],
            separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()
        return GameTasteProfile(
            owner, tuple(insights), tuple(directives),
            any(not x.user_confirmed for x in insights), fingerprint,
        )

    def erase(self, owner: str, *, authorized: bool) -> int:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("game observation erasure requires authorization")
        with self.db:
            return self.db.execute(
                "DELETE FROM dragon_game_sessions WHERE owner=?", (owner,)
            ).rowcount
