"""Local multiplayer grants, finite prediction and bounded rollback state.

These caller-held records and encryption markers do not implement or qualify a
network transport, peer authentication, encryption or distributed replication.
"""
from __future__ import annotations

import hashlib
import hmac
import time
import math
from dataclasses import dataclass, field
from typing import Dict, Final, List

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_MAX_PLAYERS: Final[int] = 128
_GRANT_TTL_S: Final[float] = 1200.0
_MAX_LAG_MS: Final[int] = 150
_INTEREST_RADIUS: Final[float] = 200.0
_ROLLBACK_WINDOW: Final[int] = 64

class MultiplayerError(SkeletonError):
    code = "MESH_MULTI"
    severity = "high"


def _identity(value: object) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 128 or not value.strip():
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    return all(ord(character) >= 32 and ord(character) != 127 for character in value)


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _vector(value: object, label: str) -> tuple[float, float, float]:
    if (type(value) not in (tuple, list) or len(value) != 3
            or any(not _finite(component) for component in value)):
        raise MultiplayerError("invalid " + label)
    # Copy caller lists without rounding observed integer coordinates.
    return tuple(value)


def _lag(value: object) -> None:
    if type(value) is not int or value < 0 or not _finite(value):
        raise MultiplayerError("invalid peer lag")


def _digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)

@dataclass
class PeerState:
    player_id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    predicted: tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_tick: int = 0
    lag_ms: int = 0
    cheat_score: float = 0.0
    interested: bool = True
    encrypted: bool = True

    @property
    def lag(self) -> int:
        """Backward-compatible observed lag in milliseconds."""
        return self.lag_ms

@dataclass
class PlayerGrant:
    player_id: str
    session_id: str
    vector_clock: tuple[int, ...]
    issued_at: float
    expires_at: float
    digest: str = ""
    encrypted: bool = True
    peers: Dict[str, PeerState] = field(default_factory=dict)
    rollback_buffer: List[dict] = field(default_factory=list)
    distributed_rollback: List[int] = field(default_factory=list)

    @property
    def rollback(self) -> List[dict]:
        return self.rollback_buffer

    @property
    def interest_set(self) -> List[str]:
        return [peer_id for peer_id, peer in self.peers.items() if peer.interested]

@dataclass
class SessionAuthority:
    session_id: str
    max_players: int = _MAX_PLAYERS
    grants: Dict[str, PlayerGrant] = field(default_factory=dict)
    clock: List[int] = field(default_factory=list)
    global_tick: int = 0

    @property
    def tick(self) -> int:
        return self.global_tick

    def sync(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag: int) -> None:
        self.distributed_sync(player_id, peer_id, pos, lag)

    def sync_peer(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag_ms: int) -> None:
        self.distributed_sync(player_id, peer_id, pos, lag_ms)

    def predictive_sync(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag_ms: int) -> None:
        self.distributed_sync(player_id, peer_id, pos, lag_ms)

    def predictive_distributed_sync(self, player_id: str, peer_id: str,
                                    pos: tuple[float, float, float],
                                    velocity: tuple[float, float, float], lag_ms: int) -> None:
        position = _vector(pos, "peer position")
        speed = _vector(velocity, "predictive velocity")
        _lag(lag_ms)
        horizon_s = min(lag_ms, _MAX_LAG_MS) / 1000.0
        predicted = _vector(tuple(point + change * horizon_s for point, change in zip(position, speed)),
                            "predictive position")
        self._sync(player_id, peer_id, position, lag_ms, predicted)

    def verify(self, player_id: str, digest: str) -> bool:
        return self.verify_grant(player_id, digest)

    def _grant_is_active(self, player_id: str, grant: PlayerGrant, now: float) -> bool:
        """Read-only issuer binding; rejected sync never revokes stored state."""
        if (type(grant) is not PlayerGrant or not _identity(self.session_id)
                or not _identity(grant.player_id) or not _identity(grant.session_id)
                or type(self.grants) is not dict
                or type(self.max_players) is not int or not 1 <= self.max_players <= _MAX_PLAYERS
                or len(self.grants) > self.max_players
                or grant.player_id != player_id or grant.session_id != self.session_id
                or grant.encrypted is not True or not _digest(grant.digest)
                or not all(_finite(value) for value in (now, grant.issued_at, grant.expires_at))
                or not grant.issued_at <= now < grant.expires_at
                or not 0 < grant.expires_at - grant.issued_at <= _GRANT_TTL_S
                or type(grant.vector_clock) is not tuple or not grant.vector_clock
                or any(type(value) is not int or not 0 <= value < 1_000_000 for value in grant.vector_clock)
                or type(grant.peers) is not dict
                or type(grant.rollback_buffer) is not list or type(grant.distributed_rollback) is not list):
            return False
        if any(not _identity(peer_id) or type(peer) is not PeerState
               or not _identity(peer.player_id) or peer.player_id != peer_id
               or not _finite(peer.cheat_score) or not 0 <= peer.cheat_score <= 2.0
               for peer_id, peer in grant.peers.items()):
            return False
        payload = f"{grant.player_id}:{grant.session_id}:{grant.vector_clock}:distenc"
        return hmac.compare_digest(grant.digest, hashlib.sha256(payload.encode()).hexdigest())

    def issue_grant(self, player_id: str) -> PlayerGrant:
        if not _identity(player_id) or not _identity(self.session_id):
            raise MultiplayerError("invalid player or session identity")
        if type(self.max_players) is not int or not 1 <= self.max_players <= _MAX_PLAYERS:
            raise MultiplayerError("invalid player limit")
        if (type(self.grants) is not dict or type(self.clock) is not list
                or any(type(value) is not int or not 0 <= value < 1_000_000 for value in self.clock)):
            raise MultiplayerError("invalid session state")
        if len(self.grants) >= self.max_players:
            raise MultiplayerError("session full")
        if player_id in self.grants:
            raise MultiplayerError("player already granted")
        now = time.time()
        if not _finite(now) or not _finite(now + _GRANT_TTL_S) or now + _GRANT_TTL_S <= now:
            raise MultiplayerError("invalid grant clock")
        self.clock.append(int(now * 1000) % 1_000_000)
        grant = PlayerGrant(
            player_id=player_id,
            session_id=self.session_id,
            vector_clock=tuple(self.clock),
            issued_at=now,
            expires_at=now + _GRANT_TTL_S,
        )
        payload = f"{grant.player_id}:{grant.session_id}:{grant.vector_clock}:distenc"
        grant.digest = hashlib.sha256(payload.encode()).hexdigest()
        self.grants[player_id] = grant
        emit_receipt(kind="multiplayer_grant_30x", target=player_id, digest=grant.digest, encrypted=True, stored_prose=0)
        return grant

    def distributed_sync(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag_ms: int) -> None:
        self._sync(player_id, peer_id, pos, lag_ms)

    def _sync(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag_ms: int,
              predicted: tuple[float, float, float] | None = None) -> None:
        if not _identity(player_id) or not _identity(peer_id):
            raise MultiplayerError("invalid player or peer identity")
        position = _vector(pos, "peer position")
        _lag(lag_ms)
        if type(self.grants) is not dict:
            raise MultiplayerError("invalid session state")
        grant = self.grants.get(player_id)
        if grant is None:
            raise MultiplayerError("no grant")
        if not self._grant_is_active(player_id, grant, time.time()):
            raise MultiplayerError("no active grant")
        if type(self.global_tick) is not int or self.global_tick < 0 or not _finite(self.global_tick):
            raise MultiplayerError("invalid session tick")
        peer = grant.peers.get(peer_id)
        previous = _vector(peer.position, "stored peer position") if peer else (0.0, 0.0, 0.0)
        if predicted is None:
            try:
                predicted = (position[0] + (position[0] - previous[0]) * 0.6, position[1], position[2])
            except OverflowError:
                raise MultiplayerError("invalid predictive position") from None
        predicted = _vector(predicted, "predictive position")
        score = (peer.cheat_score if peer else 0.0) + (0.2 if lag_ms > _MAX_LAG_MS else 0.0)
        # Every request and derived value is checked before the first mutation.
        if peer is None:
            peer = PeerState(peer_id)
            grant.peers[peer_id] = peer
        peer.cheat_score = score
        peer.predicted = predicted
        peer.position = position
        peer.lag_ms = lag_ms
        peer.last_tick = self.global_tick
        dist = math.hypot(position[0], position[1])
        peer.interested = dist < _INTEREST_RADIUS
        self.global_tick += 1
        grant.rollback_buffer.append({"tick": self.global_tick, "pos": position})
        grant.distributed_rollback.append(self.global_tick)
        del grant.rollback_buffer[:-_ROLLBACK_WINDOW]
        del grant.distributed_rollback[:-_ROLLBACK_WINDOW]
        emit_receipt(kind="multiplayer_distributed_sync", target=f"{player_id}->{peer_id}", lag=lag_ms, stored_prose=0)

    def verify_grant(self, player_id: str, digest: str) -> bool:
        if not _identity(player_id) or type(self.grants) is not dict:
            return False
        grant = self.grants.get(player_id)
        if type(grant) is not PlayerGrant:
            return False
        now = time.time()
        if (grant.encrypted is not True
                or _finite(now) and _finite(grant.expires_at) and now >= grant.expires_at):
            self.grants.pop(player_id, None)
            return False
        return (self._grant_is_active(player_id, grant, now) and _digest(digest)
                and hmac.compare_digest(grant.digest, digest))

    def revoke(self, player_id: str) -> None:
        self.grants.pop(player_id, None)
        emit_receipt(kind="multiplayer_revoke_30x", target=player_id, stored_prose=0)
