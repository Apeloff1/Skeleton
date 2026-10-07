"""In-process runtime session manager for playable simulations.

Provides the application-facing lifecycle missing from the mined mechanics:
create, inspect, step, close, and bounded retention. It is intentionally small
and storage-neutral; durable replay/checkpoint adapters can sit above it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import threading
import uuid

from core.flight_dynamics import FlightInput, FlightState
from core.playable_simulation import PlayableSimulation, SimulationFrame
from core.terrain_field import HeightField, TerrainConfig, seeded_thermals


class SessionNotFound(KeyError):
    pass


class SessionCapacityError(RuntimeError):
    pass


@dataclass(slots=True)
class RuntimeSession:
    id: str
    simulation: PlayableSimulation
    created_at: str
    updated_at: str
    closed: bool = False


class RuntimeSessionManager:
    def __init__(self, *, capacity: int = 128) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(
        self,
        *,
        seed: int = 1,
        terrain_size: float = 720.0,
        resolution: int = 96,
        thermal_count: int = 8,
        initial_state: FlightState | None = None,
    ) -> RuntimeSession:
        with self._lock:
            active = sum(not session.closed for session in self._sessions.values())
            if active >= self.capacity:
                raise SessionCapacityError("runtime session capacity reached")
            stamp = self._now()
            session = RuntimeSession(
                id=uuid.uuid4().hex,
                simulation=PlayableSimulation(
                    terrain=HeightField(
                        terrain_size,
                        resolution,
                        config=TerrainConfig(world_size=terrain_size),
                    ),
                    thermals=seeded_thermals(thermal_count, seed=seed),
                    state=initial_state,
                ),
                created_at=stamp,
                updated_at=stamp,
            )
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> RuntimeSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFound(session_id)
            return session

    def step(self, session_id: str, *, dt: float, controls: FlightInput) -> SimulationFrame:
        with self._lock:
            session = self.get(session_id)
            if session.closed:
                raise RuntimeError("runtime session is closed")
            frame = session.simulation.step(dt, controls)
            session.updated_at = self._now()
            if frame.crashed:
                session.closed = True
            return frame

    def close(self, session_id: str) -> RuntimeSession:
        with self._lock:
            session = self.get(session_id)
            session.closed = True
            session.updated_at = self._now()
            return session

    def prune_closed(self, *, keep: int = 16) -> int:
        if keep < 0:
            raise ValueError("keep cannot be negative")
        with self._lock:
            closed = sorted(
                (session for session in self._sessions.values() if session.closed),
                key=lambda session: session.updated_at,
                reverse=True,
            )
            remove = closed[keep:]
            for session in remove:
                self._sessions.pop(session.id, None)
            return len(remove)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            total = len(self._sessions)
            closed = sum(session.closed for session in self._sessions.values())
            return {"total": total, "active": total - closed, "closed": closed, "capacity": self.capacity}
