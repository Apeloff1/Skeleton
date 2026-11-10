"""In-process runtime session manager for playable simulations.

Provides the application-facing lifecycle missing from the mined mechanics:
create, inspect, step, close, and bounded retention. It is intentionally small
and storage-neutral; durable replay/checkpoint adapters can sit above it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
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
    owner: str
    simulation: PlayableSimulation
    created_at: str
    updated_at: str
    seed: int
    terrain_size: float
    resolution: int
    thermal_count: int
    closed: bool = False


class RuntimeSessionManager:
    def __init__(self, root: str | Path | None = None, *, capacity: int = 128) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.root = Path(root) if root is not None else None
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = threading.RLock()
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._restore()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(
        self,
        *,
        owner: str = "anonymous",
        seed: int = 1,
        terrain_size: float = 720.0,
        resolution: int = 96,
        thermal_count: int = 8,
        initial_state: FlightState | None = None,
    ) -> RuntimeSession:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
            raise ValueError("owner must be a non-empty string of at most 200 characters")
        if isinstance(seed, bool) or not isinstance(seed, int) or not -(2**31) <= seed < 2**31:
            raise ValueError("seed must be a signed 32-bit integer")
        if not isinstance(terrain_size, (int, float)) or isinstance(terrain_size, bool) or not math.isfinite(terrain_size) or not 64 <= terrain_size <= 10_000:
            raise ValueError("terrain_size must be finite and between 64 and 10000")
        if isinstance(resolution, bool) or not isinstance(resolution, int) or not 8 <= resolution <= 512:
            raise ValueError("resolution must be an integer between 8 and 512")
        if isinstance(thermal_count, bool) or not isinstance(thermal_count, int) or not 0 <= thermal_count <= 256:
            raise ValueError("thermal_count must be an integer between 0 and 256")
        with self._lock:
            active = sum(not session.closed for session in self._sessions.values())
            if active >= self.capacity:
                raise SessionCapacityError("runtime session capacity reached")
            stamp = self._now()
            session = RuntimeSession(
                id=uuid.uuid4().hex,
                owner=owner.strip(),
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
                seed=seed,
                terrain_size=float(terrain_size),
                resolution=resolution,
                thermal_count=thermal_count,
            )
            self._sessions[session.id] = session
            self._persist(session)
            return session

    def get(self, session_id: str, *, owner: str | None = None) -> RuntimeSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFound(session_id)
            if owner is not None and session.owner != owner:
                # Do not reveal whether a foreign session exists.
                raise SessionNotFound(session_id)
            return session

    def step(self, session_id: str, *, dt: float, controls: FlightInput, owner: str | None = None) -> SimulationFrame:
        if not isinstance(dt, (int, float)) or isinstance(dt, bool) or not math.isfinite(dt) or not 0 < dt <= 0.25:
            raise ValueError("dt must be finite and greater than 0 up to 0.25 seconds")
        with self._lock:
            session = self.get(session_id, owner=owner)
            if session.closed:
                raise RuntimeError("runtime session is closed")
            frame = session.simulation.step(dt, controls)
            session.updated_at = self._now()
            if frame.crashed:
                session.closed = True
            self._persist(session)
            return frame

    def close(self, session_id: str, *, owner: str | None = None) -> RuntimeSession:
        with self._lock:
            session = self.get(session_id, owner=owner)
            session.closed = True
            session.updated_at = self._now()
            self._persist(session)
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
                if self.root is not None:
                    (self.root / f"{session.id}.json").unlink(missing_ok=True)
            return len(remove)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            total = len(self._sessions)
            closed = sum(session.closed for session in self._sessions.values())
            return {"total": total, "active": total - closed, "closed": closed, "capacity": self.capacity}

    def inventory(self, *, owner: str, limit: int = 50) -> list[dict[str, object]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._lock:
            sessions = sorted(
                (item for item in self._sessions.values() if item.owner == owner),
                key=lambda item: item.updated_at,
                reverse=True,
            )[:limit]
            return [self._document(item, include_owner=False) for item in sessions]

    def _document(self, session: RuntimeSession, *, include_owner: bool = True) -> dict[str, object]:
        frame = session.simulation.frame()
        document: dict[str, object] = {
            "schema_version": 1,
            "session_id": session.id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "closed": session.closed,
            "seed": session.seed,
            "terrain_size": session.terrain_size,
            "resolution": session.resolution,
            "thermal_count": session.thermal_count,
            "tick": frame.tick,
            "time": frame.time,
            "state": frame.state,
        }
        if include_owner:
            document["owner"] = session.owner
        return document

    def _persist(self, session: RuntimeSession) -> None:
        if self.root is None:
            return
        target = self.root / f"{session.id}.json"
        temporary = self.root / f".{session.id}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(self._document(session), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)

    def _restore(self) -> None:
        assert self.root is not None
        # Bound startup work even if the checkpoint directory was externally filled.
        paths = sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[: self.capacity + 16]
        for path in paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("schema_version") != 1 or raw.get("session_id") != path.stem:
                    continue
                owner = raw.get("owner")
                seed = raw.get("seed")
                terrain_size = raw.get("terrain_size")
                resolution = raw.get("resolution")
                thermal_count = raw.get("thermal_count")
                tick = raw.get("tick", 0)
                elapsed = raw.get("time", 0.0)
                if not isinstance(owner, str) or not owner or len(owner) > 200:
                    continue
                if isinstance(seed, bool) or not isinstance(seed, int) or not -(2**31) <= seed < 2**31:
                    continue
                if not isinstance(terrain_size, (int, float)) or isinstance(terrain_size, bool) or not math.isfinite(terrain_size) or not 64 <= terrain_size <= 10_000:
                    continue
                if isinstance(resolution, bool) or not isinstance(resolution, int) or not 8 <= resolution <= 512:
                    continue
                if isinstance(thermal_count, bool) or not isinstance(thermal_count, int) or not 0 <= thermal_count <= 256:
                    continue
                if isinstance(tick, bool) or not isinstance(tick, int) or not 0 <= tick <= 2**63 - 1:
                    continue
                if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
                    continue
                state = FlightState(**raw["state"])
                if any(not math.isfinite(getattr(state, field)) for field in ("x", "y", "z", "yaw", "pitch", "bank", "speed")):
                    continue
                session = RuntimeSession(
                    id=path.stem,
                    owner=owner,
                    simulation=PlayableSimulation(
                        terrain=HeightField(float(terrain_size), resolution, config=TerrainConfig(world_size=float(terrain_size))),
                        thermals=seeded_thermals(thermal_count, seed=seed),
                        state=state,
                    ),
                    created_at=str(raw["created_at"]),
                    updated_at=str(raw["updated_at"]),
                    seed=seed,
                    terrain_size=float(terrain_size),
                    resolution=resolution,
                    thermal_count=thermal_count,
                    closed=bool(raw["closed"]),
                )
                session.simulation.tick = tick
                session.simulation.time = float(elapsed)
                self._sessions[session.id] = session
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                # A corrupt checkpoint cannot become authoritative runtime state.
                continue
