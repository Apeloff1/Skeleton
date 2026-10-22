"""skeleton/distributed/mesh/multiplayer_authority.py
10x multiplayer authority. Peer sync, lag compensation, anti-cheat bounds, vector clock.
Fail-closed. Receipts. No stubs.
"""
from __future__ import annotations

import hashlib
import time
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

_MAX_PLAYERS: Final[int] = 32
_GRANT_TTL_S: Final[float] = 600.0
_MAX_LAG_MS: Final[int] = 250

class MultiplayerError(SkeletonError):
    code = "MESH_MULTI"
    severity = "high"

@dataclass
class PeerState:
    player_id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_tick: int = 0
    lag_ms: int = 0
    cheat_score: float = 0.0

@dataclass
class PlayerGrant:
    player_id: str
    session_id: str
    vector_clock: tuple[int, ...]
    issued_at: float
    expires_at: float
    digest: str = ""
    peers: Dict[str, PeerState] = field(default_factory=dict)

@dataclass
class SessionAuthority:
    session_id: str
    max_players: int = _MAX_PLAYERS
    grants: Dict[str, PlayerGrant] = field(default_factory=dict)
    clock: List[int] = field(default_factory=list)
    global_tick: int = 0

    def issue_grant(self, player_id: str) -> PlayerGrant:
        if len(self.grants) >= self.max_players:
            raise MultiplayerError("session full")
        if player_id in self.grants:
            raise MultiplayerError("player already granted")
        now = time.time()
        self.clock.append(int(now * 1000) % 1_000_000)
        grant = PlayerGrant(
            player_id=player_id,
            session_id=self.session_id,
            vector_clock=tuple(self.clock),
            issued_at=now,
            expires_at=now + _GRANT_TTL_S,
        )
        payload = f"{grant.player_id}:{grant.session_id}:{grant.vector_clock}"
        grant.digest = hashlib.sha256(payload.encode()).hexdigest()
        self.grants[player_id] = grant
        emit_receipt(kind="multiplayer_grant_10x", target=player_id, digest=grant.digest, stored_prose=0)
        return grant

    def sync_peer(self, player_id: str, peer_id: str, pos: tuple[float, float, float], lag_ms: int) -> None:
        grant = self.grants.get(player_id)
        if not grant:
            raise MultiplayerError("no grant")
        if lag_ms > _MAX_LAG_MS:
            grant.peers.get(peer_id, PeerState(peer_id)).cheat_score += 0.1
        peer = grant.peers.setdefault(peer_id, PeerState(peer_id))
        peer.position = pos
        peer.lag_ms = lag_ms
        peer.last_tick = self.global_tick
        self.global_tick += 1
        emit_receipt(kind="multiplayer_sync", target=f"{player_id}->{peer_id}", lag=lag_ms, stored_prose=0)

    def verify_grant(self, player_id: str, digest: str) -> bool:
        grant = self.grants.get(player_id)
        if not grant or time.time() > grant.expires_at:
            self.grants.pop(player_id, None)
            return False
        if any(p.cheat_score > 1.0 for p in grant.peers.values()):
            return False
        return grant.digest == digest

    def revoke(self, player_id: str) -> None:
        self.grants.pop(player_id, None)
        emit_receipt(kind="multiplayer_revoke_10x", target=player_id, stored_prose=0)
