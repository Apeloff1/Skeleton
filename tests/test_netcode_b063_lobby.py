"""B063: players form sessions with explicit lifecycle, permissions and abuse controls."""
import base64

import pytest

from skeleton.netcode.lobby import (TRANSITIONS, InviteCodec, InviteError, Lobby, LobbyError, LobbyState,
                                    RateLimiter, Role)

KEY = b"k" * 32


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


def _lobby(clock, **kw):
    return Lobby("L1", "host", InviteCodec(KEY, clock), clock, **kw)


def test_b063_lifecycle_created_open_full_in_game_closed(clock):
    lb = _lobby(clock, capacity=2)
    assert lb.state is LobbyState.CREATED
    lb.open("host")
    lb.join("p1", lb.invite("host"))
    assert lb.state is LobbyState.FULL
    lb.start("host")
    assert lb.state is LobbyState.IN_GAME
    lb.close("host")
    assert lb.state is LobbyState.CLOSED
    assert TRANSITIONS[LobbyState.CLOSED] == frozenset()


def test_b063_lifecycle_rejects_illegal_transitions(clock):
    lb = _lobby(clock)
    with pytest.raises(LobbyError):
        lb.start("host")  # CREATED -> IN_GAME is illegal and needs players
    lb.open("host")
    lb.close("host")
    with pytest.raises(LobbyError):
        lb.open("host")


def test_b063_full_returns_to_open_when_member_leaves(clock):
    lb = _lobby(clock, capacity=2)
    lb.open("host")
    lb.join("p1", lb.invite("host"))
    lb.leave("p1")
    assert lb.state is LobbyState.OPEN


def test_b063_permissions_host_only_actions(clock):
    lb = _lobby(clock)
    lb.open("host")
    lb.join("p1", lb.invite("host"))
    for action in (lambda: lb.start("p1"), lambda: lb.close("p1"), lambda: lb.kick("p1", "host")):
        with pytest.raises(LobbyError):
            action()
    with pytest.raises(LobbyError):
        lb.invite("stranger")


def test_b063_host_migration_on_host_leave(clock):
    lb = _lobby(clock)
    lb.open("host")
    lb.join("p1", lb.invite("host"))
    lb.leave("host")
    assert lb.host == "p1" and lb.members["p1"] is Role.HOST


def test_b063_private_lobby_requires_invite(clock):
    lb = _lobby(clock)
    lb.open("host")
    with pytest.raises(LobbyError):
        lb.join("p1")


def test_b063_invite_expires(clock):
    lb = _lobby(clock)
    lb.open("host")
    tok = lb.invite("host", ttl_s=60)
    clock.t += 61
    with pytest.raises(InviteError):
        lb.join("p1", tok)


def test_b063_invite_is_single_use_and_lobby_bound(clock):
    lb = _lobby(clock)
    other = Lobby("L2", "h2", InviteCodec(KEY, clock), clock)
    other.open("h2")
    lb.open("host")
    tok = lb.invite("host")
    with pytest.raises(InviteError):
        other.join("p1", tok)
    lb.join("p1", tok)
    with pytest.raises(InviteError):
        lb.join("p2", tok)


def test_b063_invite_tampering_and_forgery_rejected(clock):
    codec = InviteCodec(KEY, clock)
    tok = codec.issue("L1")
    raw = bytearray(base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)))
    raw[20] ^= 1  # push expiry
    bad = base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
    for t in (bad, "!!!", "", InviteCodec(b"x" * 32, clock).issue("L1")):
        with pytest.raises(InviteError):
            codec.verify(t, "L1")


def test_b063_invite_token_carries_no_secrets_or_player_data(clock):
    codec = InviteCodec(KEY, clock)
    raw = base64.urlsafe_b64decode(codec.issue("L1-secret-name") + "==")
    assert KEY not in raw and b"L1-secret-name" not in raw and b"host" not in raw
    assert len(raw) == 48


def test_b063_invite_key_must_be_strong(clock):
    with pytest.raises(ValueError):
        InviteCodec(b"short", clock)


def test_b063_kick_and_ban(clock):
    lb = _lobby(clock)
    lb.open("host")
    lb.join("p1", lb.invite("host"))
    lb.kick("host", "p1", ban=True)
    assert "p1" not in lb.members
    with pytest.raises(LobbyError, match="banned"):
        lb.join("p1", lb.invite("host"))
    with pytest.raises(LobbyError):
        lb.kick("host", "host")


def test_b063_join_flood_is_rate_limited(clock):
    lb = _lobby(clock, capacity=64, public=True)
    lb.open("host")
    results = []
    for i in range(20):
        try:
            lb.join(f"bot{i}")
            results.append(True)
        except LobbyError:
            results.append(False)
    assert results.count(True) == 5  # lobby-wide burst
    assert ("rate_limited", "bot5", "") in lb.audit
    clock.t += 10
    lb.join("late")


def test_b063_rate_limiter_per_key_refills(clock):
    rl = RateLimiter(1.0, 2, clock)
    assert [rl.allow("a") for _ in range(3)] == [True, True, False]
    assert rl.allow("b")
    clock.t += 1
    assert rl.allow("a")
