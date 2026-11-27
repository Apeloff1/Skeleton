"""Local state admission and compatibility; no sockets, transport or encryption proof."""
from dataclasses import asdict
import json

import pytest

from skeleton.distributed.mesh import multiplayer_authority as owner


@pytest.fixture
def state(monkeypatch):
    clock = [1000.0]
    receipts = []
    monkeypatch.setattr(owner.time, "time", lambda: clock[0])
    monkeypatch.setattr(owner, "emit_receipt", lambda **receipt: receipts.append(receipt))
    authority = owner.SessionAuthority("session")
    grant = authority.issue_grant("player")
    receipts.clear()
    return authority, grant, clock, receipts


def frozen(authority):
    return json.dumps(asdict(authority), sort_keys=True, allow_nan=True)


def denied(state, operation):
    authority, grant, _, receipts = state
    before = frozen(authority)
    receipts.clear()
    with pytest.raises(owner.MultiplayerError):
        operation()
    assert frozen(authority) == before
    assert authority.grants.get("player") is grant
    assert receipts == []


@pytest.mark.parametrize("position", [None, "1,2,3", {}, (1, 2), (1, 2, 3, 4),
    (True, 0, 0), ("1", 0, 0), (float("nan"), 0, 0),
    (float("inf"), 0, 0), (-float("inf"), 0, 0), (10**400, 0, 0)])
def test_direct_sync_rejects_invalid_positions_before_any_mutation(state, position):
    denied(state, lambda: state[0].distributed_sync("player", "peer", position, 20))


@pytest.mark.parametrize("lag", [-1, True, False, 1.0, float("nan"), float("inf"), "30", None, 10**400])
def test_direct_sync_rejects_invalid_lag_before_any_mutation(state, lag):
    denied(state, lambda: state[0].distributed_sync("player", "peer", (1, 2, 3), lag))


@pytest.mark.parametrize("peer", ["", " ", "line\nbreak", "x" * 129, "\ud800", 1, None, [], {}])
def test_peer_identity_is_strict_without_inserting_unvalidated_keys(state, peer):
    denied(state, lambda: state[0].distributed_sync("player", peer, (1, 2, 3), 20))


@pytest.mark.parametrize("attribute,value", [("expires_at", 1000.0), ("expires_at", 999.0),
    ("encrypted", False), ("encrypted", 1), ("digest", "f" * 64), ("player_id", "another"),
    ("session_id", "another-session"), ("vector_clock", (2,)), ("issued_at", 1001.0),
    ("expires_at", float("inf")), ("expires_at", 2201.0), ("issued_at", float("nan"))])
@pytest.mark.parametrize("predictive", [False, True])
def test_both_sync_paths_require_a_valid_unexpired_issuer_binding_without_revocation(state, attribute, value, predictive):
    authority, grant, _, _ = state
    setattr(grant, attribute, value)
    operation = (lambda: authority.predictive_distributed_sync("player", "peer", (1, 2, 3), (1, 0, 0), 20)) if predictive else (
        lambda: authority.distributed_sync("player", "peer", (1, 2, 3), 20))
    denied(state, operation)


@pytest.mark.parametrize("velocity", [(True, 0, 0), (float("nan"), 0, 0),
    (float("inf"), 0, 0), (10**400, 0, 0), (1, 2), "fast"])
def test_predictive_velocity_is_checked_before_tick_peer_or_receipt_changes(state, velocity):
    denied(state, lambda: state[0].predictive_distributed_sync("player", "peer", (1, 2, 3), velocity, 20))


def test_derived_prediction_overflow_is_rejected_before_state_changes(state):
    authority = state[0]
    denied(state, lambda: authority.distributed_sync("player", "peer", (1.7e308, 0, 0), 20))
    denied(state, lambda: authority.predictive_distributed_sync("player", "peer", (1.7e308, 0, 0), (1.7e308, 0, 0), 150))
    # The explicit velocity path is independent of an overflowing legacy
    # extrapolator, so an actually finite prediction remains admissible.
    authority.predictive_distributed_sync("player", "peer", (1.7e308, 0, 0), (0, 0, 0), 150)
    assert state[1].peers["peer"].predicted == (1.7e308, 0.0, 0.0)
    authority.predictive_distributed_sync("player", "peer", (10**308, 0, 0), (0, 0, 0), 0)
    denied(state, lambda: authority.distributed_sync("player", "peer", (-10**308, 0, 0), 20))


def test_legacy_aliases_share_strict_admission_and_public_read_properties(state):
    authority, grant, _, _ = state
    for method in (authority.sync, authority.sync_peer, authority.predictive_sync, authority.distributed_sync):
        denied(state, lambda: method("player", "peer", (1, 2, 3), True))
        method("player", "peer", (1, 2, 3), 12)
    assert authority.tick == 4
    assert authority.verify("player", grant.digest)
    assert grant.rollback is grant.rollback_buffer
    assert grant.peers["peer"].lag == 12
    assert grant.interest_set == ["peer"]


def test_first_high_lag_strike_is_retained_and_later_denial_preserves_state(state):
    authority, grant, _, _ = state
    authority.sync_peer("player", "peer", (1, 2, 3), 151)
    assert grant.peers["peer"].cheat_score == pytest.approx(0.2)
    for _ in range(10):
        authority.sync_peer("player", "peer", (1, 2, 3), 151)
    assert grant.peers["peer"].cheat_score > 2.0
    assert not authority.verify_grant("player", grant.digest)
    denied(state, lambda: authority.sync_peer("player", "peer", (1, 2, 3), 20))


def test_predictive_horizon_is_capped_without_discarding_actual_high_lag(state):
    authority, grant, _, _ = state
    authority.predictive_distributed_sync("player", "peer", [20, 30, 0], [5, 2, 0], 300)
    peer = grant.peers["peer"]
    assert peer.predicted == pytest.approx((20.75, 30.3, 0))
    assert peer.position == (20.0, 30.0, 0.0) and peer.lag_ms == 300
    assert peer.cheat_score == pytest.approx(0.2)


def test_both_rollback_lists_keep_exact_latest_64_frames_and_inputs_cannot_alias_state(state):
    authority, grant, _, _ = state
    source_position = [0, 1, 2]
    authority.distributed_sync("player", "peer", source_position, 12)
    source_position[0] = 999
    assert grant.peers["peer"].position == (0, 1, 2)
    assert grant.rollback_buffer[0]["pos"] == (0, 1, 2)
    for step in range(1, 100):
        authority.distributed_sync("player", "peer", (step, 1, 2), 12)
    assert authority.global_tick == 100
    assert len(grant.rollback_buffer) == len(grant.distributed_rollback) == 64
    assert [frame["tick"] for frame in grant.rollback_buffer] == grant.distributed_rollback == list(range(37, 101))
    assert grant.rollback_buffer[0]["pos"] == (36, 1, 2)
    assert grant.rollback_buffer[-1]["pos"] == (99, 1, 2)


def test_observed_integer_coordinates_are_not_silently_rounded_to_float(state):
    authority, grant, _, _ = state
    exact = 2**60 + 1
    authority.distributed_sync("player", "peer", [exact, 1, 2], 12)
    assert grant.peers["peer"].position[0] == exact
    assert type(grant.peers["peer"].position[0]) is int
    assert grant.rollback_buffer[-1]["pos"][0] == exact


def test_missing_grant_and_expiry_never_implicitly_mutate_sync_state(state):
    authority, grant, clock, receipts = state
    denied(state, lambda: authority.distributed_sync("unknown", "peer", (0, 0, 0), 0))
    clock[0] = grant.expires_at
    denied(state, lambda: authority.distributed_sync("player", "peer", (0, 0, 0), 0))
    # Preserve the legacy explicit verification lifecycle separately from sync.
    assert not authority.verify_grant("player", grant.digest)
    assert authority.grants == {} and receipts == []


def test_new_issuer_clock_entries_do_not_invalidate_prior_grant_snapshots(state):
    authority, grant, _, _ = state
    original_clock, original_digest = grant.vector_clock, grant.digest
    authority.issue_grant("another-player")
    assert grant.vector_clock == original_clock and grant.digest == original_digest
    assert authority.verify_grant("player", original_digest)
    authority.distributed_sync("player", "peer", (1, 2, 3), 20)


def test_default_128_player_cap_cannot_be_widened_and_cap_denial_is_atomic(state):
    authority, _, _, receipts = state
    assert authority.max_players == 128
    for index in range(127):
        authority.issue_grant("additional-" + str(index))
    assert len(authority.grants) == 128
    denied(state, lambda: authority.issue_grant("one-too-many"))
    assert receipts == []


@pytest.mark.parametrize("limit", [129, 256, 0, -1, True, 1.5])
def test_invalid_configured_player_limits_never_admit_a_grant(state, limit):
    receipts = state[3]; receipts.clear()
    authority = owner.SessionAuthority("session", max_players=limit)
    with pytest.raises(owner.MultiplayerError):
        authority.issue_grant("player")
    assert authority.grants == {} and authority.clock == [] and receipts == []


@pytest.mark.parametrize("player", ["", "\nforged", "\ud800", [], None])
def test_invalid_grant_identity_never_advances_clock_or_emits_receipt(state, player):
    denied(state, lambda: state[0].issue_grant(player))


def test_corrupt_peer_or_unknown_clock_is_not_a_new_prediction_authority(state):
    authority, grant, clock, _ = state
    authority.distributed_sync("player", "peer", (1, 2, 3), 20)
    grant.peers["peer"].position = (float("nan"), 0, 0)
    denied(state, lambda: authority.distributed_sync("player", "peer", (4, 5, 6), 20))
    grant.peers["peer"].position = (1, 2, 3)
    clock[0] = float("nan")
    denied(state, lambda: authority.distributed_sync("player", "peer", (4, 5, 6), 20))
