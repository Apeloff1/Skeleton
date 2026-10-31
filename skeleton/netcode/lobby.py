"""B063 - lobby/invite/session service with explicit lifecycle and abuse controls.

Lifecycle: CREATED -> OPEN <-> FULL -> IN_GAME -> CLOSED (CLOSED is terminal).
Invites are opaque HMAC-signed tokens carrying only lobby id, expiry and a
nonce - never player data or secrets. The signing key is held server-side.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class LobbyError(PermissionError):
    pass


class InviteError(ValueError):
    pass


class LobbyState(str, Enum):
    CREATED = "created"
    OPEN = "open"
    FULL = "full"
    IN_GAME = "in_game"
    CLOSED = "closed"


TRANSITIONS: dict[LobbyState, frozenset[LobbyState]] = {
    LobbyState.CREATED: frozenset({LobbyState.OPEN, LobbyState.CLOSED}),
    LobbyState.OPEN: frozenset({LobbyState.FULL, LobbyState.IN_GAME, LobbyState.CLOSED}),
    LobbyState.FULL: frozenset({LobbyState.OPEN, LobbyState.IN_GAME, LobbyState.CLOSED}),
    LobbyState.IN_GAME: frozenset({LobbyState.CLOSED}),
    LobbyState.CLOSED: frozenset(),
}


class Role(str, Enum):
    HOST = "host"
    MEMBER = "member"


class RateLimiter:
    """Token bucket per key, driven by an injectable clock (deterministic in tests)."""

    def __init__(self, rate_per_s: float, burst: int, clock: Callable[[], float]) -> None:
        self.rate, self.burst, self.clock = rate_per_s, burst, clock
        self._b: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        tokens, last = self._b.get(key, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens < 1:
            self._b[key] = (tokens, now)
            return False
        self._b[key] = (tokens - 1, now)
        if len(self._b) > 10_000:  # bound memory under key-spray
            self._b.pop(next(iter(self._b)))
        return True


_TOK = struct.Struct(">16sQ8s")


class InviteCodec:
    def __init__(self, key: bytes, clock: Callable[[], float]) -> None:
        if len(key) < 32:
            raise ValueError("invite key must be >= 32 bytes")
        self._key, self.clock = key, clock

    def issue(self, lobby_id: str, ttl_s: int = 600) -> str:
        lid = hashlib.sha256(lobby_id.encode()).digest()[:16]
        body = _TOK.pack(lid, int(self.clock()) + ttl_s, secrets.token_bytes(8))
        mac = hmac.new(self._key, body, hashlib.sha256).digest()[:16]
        return base64.urlsafe_b64encode(body + mac).decode().rstrip("=")

    def verify(self, token: str, lobby_id: str) -> bytes:
        """Return the nonce if valid for ``lobby_id``; raise InviteError otherwise."""
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        except (ValueError, TypeError):
            raise InviteError("malformed invite") from None
        if len(raw) != _TOK.size + 16:
            raise InviteError("malformed invite")
        body, mac = raw[: _TOK.size], raw[_TOK.size:]
        if not hmac.compare_digest(mac, hmac.new(self._key, body, hashlib.sha256).digest()[:16]):
            raise InviteError("bad signature")
        lid, exp, nonce = _TOK.unpack(body)
        if not hmac.compare_digest(lid, hashlib.sha256(lobby_id.encode()).digest()[:16]):
            raise InviteError("wrong lobby")
        if self.clock() >= exp:
            raise InviteError("expired")
        return nonce


@dataclass
class Lobby:
    lobby_id: str
    host: str
    invites: InviteCodec
    clock: Callable[[], float]
    capacity: int = 8
    public: bool = False
    join_rate: RateLimiter | None = None
    state: LobbyState = LobbyState.CREATED
    members: dict[str, Role] = field(default_factory=dict)
    banned: set[str] = field(default_factory=set)
    used_nonces: set[bytes] = field(default_factory=set)
    audit: list[tuple[str, str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 2 <= self.capacity <= 64:
            raise ValueError("capacity out of range")
        self.members[self.host] = Role.HOST
        if self.join_rate is None:
            self.join_rate = RateLimiter(rate_per_s=2.0, burst=5, clock=self.clock)

    # lifecycle -----------------------------------------------------------
    def _to(self, new: LobbyState) -> None:
        if new not in TRANSITIONS[self.state]:
            raise LobbyError(f"illegal transition {self.state.value}->{new.value}")
        self.audit.append(("transition", self.state.value, new.value))
        self.state = new

    def _require_host(self, actor: str) -> None:
        if self.members.get(actor) is not Role.HOST:
            raise LobbyError("host only")

    def open(self, actor: str) -> None:
        self._require_host(actor)
        self._to(LobbyState.OPEN)

    def start(self, actor: str) -> None:
        self._require_host(actor)
        if len(self.members) < 2:
            raise LobbyError("need at least 2 players")
        self._to(LobbyState.IN_GAME)

    def close(self, actor: str) -> None:
        self._require_host(actor)
        self._to(LobbyState.CLOSED)

    # membership ------------------------------------------------------------
    def invite(self, actor: str, ttl_s: int = 600) -> str:
        if actor not in self.members:
            raise LobbyError("members only")
        if self.state in (LobbyState.IN_GAME, LobbyState.CLOSED):
            raise LobbyError("lobby not joinable")
        return self.invites.issue(self.lobby_id, ttl_s)

    def join(self, player: str, token: str | None = None) -> None:
        if not self.join_rate.allow(player) or not self.join_rate.allow("*lobby*"):
            self.audit.append(("rate_limited", player, ""))
            raise LobbyError("rate limited")
        if player in self.banned:
            raise LobbyError("banned")
        if self.state is not LobbyState.OPEN:
            raise LobbyError("lobby not open")
        if player in self.members:
            raise LobbyError("already a member")
        if token is None:
            if not self.public:
                raise LobbyError("invite required")
        else:
            nonce = self.invites.verify(token, self.lobby_id)
            if nonce in self.used_nonces:
                raise InviteError("invite already used")
            self.used_nonces.add(nonce)
        self.members[player] = Role.MEMBER
        self.audit.append(("join", player, ""))
        if len(self.members) >= self.capacity:
            self._to(LobbyState.FULL)

    def leave(self, player: str) -> None:
        if player not in self.members:
            raise LobbyError("not a member")
        role = self.members.pop(player)
        self.audit.append(("leave", player, ""))
        if not self.members:
            if self.state is not LobbyState.CLOSED:
                self._to(LobbyState.CLOSED)
            return
        if role is Role.HOST:  # deterministic host migration: oldest remaining member
            nxt = next(iter(self.members))
            self.members[nxt] = Role.HOST
            self.host = nxt
            self.audit.append(("host_migrated", player, nxt))
        if self.state is LobbyState.FULL:
            self._to(LobbyState.OPEN)

    def kick(self, actor: str, target: str, ban: bool = False) -> None:
        self._require_host(actor)
        if target == actor:
            raise LobbyError("host cannot kick self")
        if target in self.members:
            self.leave(target)
        if ban:
            self.banned.add(target)
        self.audit.append(("ban" if ban else "kick", actor, target))
