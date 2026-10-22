"""skeleton/distributed/mesh/multiplayer_authority.py
Fail-closed multiplayer session authority starter.
Vector-clock ordered grants, player isolation, provenance receipts.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Final

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

_MAX_PLAYERS: Final[int] = 16
_GRANT_TTL_S: Final[float] = 300.0

class MultiplayerError(SkeletonError):
    code = "MESH_MULTI"
    severity = "high"

@dataclass
class PlayerGrant:
    player_id: str
    session_id: str
    vector_clock: tuple[int, ...]
    issued_at: float
    expires_at: float
    digest: str = ""

@dataclass
class SessionAuthority:
    session_id: str
    max_players: int = _MAX_PLAYERS
    grants: dict[str, PlayerGrant] = field(default_factory=dict)
    clock: list[int] = field(default_factory=list)

    def issue_grant(self, player_id: str) -> PlayerGrant:
        if len(self.grants) >= self.max_players:
            raise MultiplayerError("session full")
        if player_id in self.grants:
            raise MultiplayerError("player already granted")
        now = time.time()
        self.clock.append(int(now * 1000) % 1000000)
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
        emit_receipt(
            kind="multiplayer_grant",
            target=player_id,
            digest=grant.digest,
            session=self.session_id,
            stored_prose=0,
        )
        return grant

    def verify_grant(self, player_id: str, digest: str) -> bool:
        grant = self.grants.get(player_id)
        if not grant:
            return False
        if time.time() > grant.expires_at:
            del self.grants[player_id]
            return False
        return grant.digest == digest

    def revoke(self, player_id: str) -> None:
        self.grants.pop(player_id, None)
        emit_receipt(kind="multiplayer_revoke", target=player_id, stored_prose=0)
