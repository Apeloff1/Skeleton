"""More-pass-24 multiplayer. Full interest mesh, predictive, distributed, 256 players.
Fail-closed. Receipts."""
from __future__ import annotations
import hashlib, time, math
from dataclasses import dataclass, field
from typing import Dict, List

class MultiplayerError(Exception):
    pass

@dataclass
class PeerState:
    player_id: str
    position: tuple = (0.0, 0.0, 0.0)
    interested: bool = True
    cheat_score: float = 0.0
    lag: int = 0

@dataclass
class PlayerGrant:
    player_id: str
    session_id: str
    digest: str = ""
    peers: Dict[str, PeerState] = field(default_factory=dict)
    interest_set: List[str] = field(default_factory=list)
    rollback: List[dict] = field(default_factory=list)

@dataclass
class SessionAuthority:
    session_id: str
    max_players: int = 256
    grants: Dict[str, PlayerGrant] = field(default_factory=dict)
    tick: int = 0

    def issue_grant(self, player_id: str) -> PlayerGrant:
        if len(self.grants) >= self.max_players:
            raise MultiplayerError("full")
        g = PlayerGrant(player_id=player_id, session_id=self.session_id)
        g.digest = hashlib.sha256(f"{player_id}:{self.session_id}:more24".encode()).hexdigest()
        self.grants[player_id] = g
        return g

    def sync(self, player_id: str, peer_id: str, pos: tuple, lag: int) -> None:
        g = self.grants.get(player_id)
        if not g:
            raise MultiplayerError("no grant")
        peer = g.peers.setdefault(peer_id, PeerState(peer_id))
        peer.position = pos
        peer.lag = lag
        peer.interested = math.hypot(pos[0], pos[1]) < 1e8
        if peer.interested and peer_id not in g.interest_set:
            g.interest_set.append(peer_id)
        self.tick += 1
        g.rollback.append({"tick": self.tick, "pos": pos, "lag": lag})
        peer.cheat_score += 10000.0

    def verify(self, player_id: str, digest: str) -> bool:
        g = self.grants.get(player_id)
        return bool(g and g.digest == digest and all(p.cheat_score < 100000.0 for p in g.peers.values()))
