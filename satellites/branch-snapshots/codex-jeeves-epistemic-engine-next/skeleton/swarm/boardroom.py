"""Boardroom — the inner court's session ledger.

Port of gameforge-rs ``crates/gf-gameforge/src/boardroom.rs``. Where the
zaibatsu's directors convene. A **session** is opened with an agenda,
minutes are minuted as motions, and each motion must cross the high court
before it becomes a **resolution**. Nothing in the boardroom is decided by
presence alone — the quorum gate stands between a motion and its force.
Sessions close with a summary that lands on the fabric: the empire's memory
of what its rulers actually agreed.

``Motion.resolution_event`` holds a fabric / merkle event id once the high
court has spoken (same as RS). Callers that already journal via
``skeleton.kernel.merkle_log.MerkleEventLog`` may pass that append's
``event_id`` into ``resolve_motion`` — extend-only; the merkle log itself
is unchanged.

This is the forge-path session ledger, **not** the file-versioning vault
under ``backend/gameforge/boardroom/``.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from skeleton.kernel.errors import SkeletonError


class BoardroomError(SkeletonError):
    """Boardroom refuse — closed chamber, already settled, unknown id."""

    code = "SWM.BOARDROOM"
    http_status = 409


class MotionStatus(str, Enum):
    TABLED = "tabled"
    RESOLVED = "resolved"
    REJECTED = "rejected"


@dataclass
class Motion:
    """One tabled minute awaiting (or carrying) the court's verdict."""

    id: str
    session_id: str
    text: str
    mover: str
    tabled_at: float
    status: MotionStatus = MotionStatus.TABLED
    # Fabric / merkle event id once resolved — the motion's provenance.
    resolution_event: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "text": self.text,
            "mover": self.mover,
            "tabled_at": self.tabled_at,
            "status": self.status.value,
            "resolution_event": self.resolution_event,
        }


@dataclass
class Session:
    """An open (or adjourned) chamber sitting."""

    id: str
    title: str
    agenda: list[str]
    opened: float
    chair: str
    closed: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "agenda": list(self.agenda),
            "opened": self.opened,
            "closed": self.closed,
            "chair": self.chair,
        }


class Boardroom:
    """In-process session + motion ledger.

    Thread-safe via a single RLock (mirrors the RS RwLock covering session /
    motion mutation so observers never see a half-written chamber).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._motions: dict[str, Motion] = {}

    def convene(
        self, title: str, chair: str, agenda: list[str] | None = None
    ) -> Session:
        """Open a session with an agenda. Returns the new Session."""
        session = Session(
            id=str(uuid.uuid4()),
            title=title,
            agenda=list(agenda or []),
            opened=time.time(),
            closed=None,
            chair=chair,
        )
        with self._lock:
            self._sessions[session.id] = session
            return Session(
                id=session.id,
                title=session.title,
                agenda=list(session.agenda),
                opened=session.opened,
                closed=session.closed,
                chair=session.chair,
            )

    def table_motion(
        self, session_id: str, mover: str, text: str
    ) -> Optional[tuple[Motion, str]]:
        """Table a motion in an open session.

        Returns ``(motion, proposal_id)`` for the high court to attest on,
        or ``None`` if the session is missing / already closed.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.closed is not None:
                return None  # no motions in a closed (or ghost) chamber
            motion = Motion(
                id=str(uuid.uuid4()),
                session_id=session_id,
                text=text,
                mover=mover,
                tabled_at=time.time(),
                status=MotionStatus.TABLED,
                resolution_event=None,
            )
            proposal_id = f"motion:{motion.id}"
            self._motions[motion.id] = motion
            return (
                Motion(
                    id=motion.id,
                    session_id=motion.session_id,
                    text=motion.text,
                    mover=motion.mover,
                    tabled_at=motion.tabled_at,
                    status=motion.status,
                    resolution_event=motion.resolution_event,
                ),
                proposal_id,
            )

    def resolve_motion(
        self,
        motion_id: str,
        carried: bool,
        event_id: Optional[str] = None,
    ) -> Optional[Motion]:
        """Record the court's verdict. Called only when the high court has spoken.

        ``event_id`` is the fabric / merkle event id once resolved (RS
        ``resolution_event``). The boardroom never resolves itself.
        """
        with self._lock:
            motion = self._motions.get(motion_id)
            if motion is None or motion.status is not MotionStatus.TABLED:
                return None
            motion.status = (
                MotionStatus.RESOLVED if carried else MotionStatus.REJECTED
            )
            motion.resolution_event = event_id
            return Motion(
                id=motion.id,
                session_id=motion.session_id,
                text=motion.text,
                mover=motion.mover,
                tabled_at=motion.tabled_at,
                status=motion.status,
                resolution_event=motion.resolution_event,
            )

    def adjourn(self, session_id: str) -> Optional[Session]:
        """Close an open session. Returns None if missing or already closed."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.closed is not None:
                return None
            session.closed = time.time()
            return Session(
                id=session.id,
                title=session.title,
                agenda=list(session.agenda),
                opened=session.opened,
                closed=session.closed,
                chair=session.chair,
            )

    def session_motions(self, session_id: str) -> list[Motion]:
        with self._lock:
            return [
                Motion(
                    id=m.id,
                    session_id=m.session_id,
                    text=m.text,
                    mover=m.mover,
                    tabled_at=m.tabled_at,
                    status=m.status,
                    resolution_event=m.resolution_event,
                )
                for m in self._motions.values()
                if m.session_id == session_id
            ]

    def sessions(self) -> list[Session]:
        with self._lock:
            return [
                Session(
                    id=s.id,
                    title=s.title,
                    agenda=list(s.agenda),
                    opened=s.opened,
                    closed=s.closed,
                    chair=s.chair,
                )
                for s in self._sessions.values()
            ]
