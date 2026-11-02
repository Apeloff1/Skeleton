"""GF-L / GF-P2-40: dynamic route repair over signed approved routes."""

import hashlib
import hmac

import pytest

from skeleton.frontier_nav.gps import FrameGPSHub, PositionFix
from skeleton.frontier_nav.route_grounding import (
    ApprovedRoute,
    DesignNote,
    RouteGrounder,
    hmac_verifier,
)
from skeleton.frontier_nav.route_repair import (
    Blockages,
    RepairFailed,
    RepairTrigger,
    RouteMonitor,
    RouteRepairer,
    WorldChange,
    point_segment_distance,
)

KEY = b"k" * 32
COORDS = {"A": (0.0, 0.0, 0.0), "B": (10.0, 0.0, 0.0), "C": (20.0, 0.0, 0.0),
          "D": (10.0, 10.0, 0.0), "E": (10.0, -30.0, 0.0)}


def note(nid, body="ok"):
    sig = hmac.new(KEY, f"{nid}\n{body}".encode(), hashlib.sha256).hexdigest()
    return DesignNote(nid, body, sig)


def setup(extra=()):
    g = RouteGrounder(hmac_verifier(KEY))
    g.approve(ApprovedRoute("main", ("A", "B", "C"), note("n1")))
    g.approve(ApprovedRoute("hill", ("A", "D", "C"), note("n2")))
    for r in extra:
        g.approve(r)
    return g, RouteRepairer(g, COORDS)


def test_world_change_validation_and_idempotence():
    with pytest.raises(ValueError):
        WorldChange("x", "meteor", 1)
    b = Blockages()
    ch = WorldChange("f1", "flood", 5, blocked_waypoints=frozenset({"B"}))
    assert b.apply(ch) and not b.apply(ch)
    with pytest.raises(ValueError):
        b.apply(WorldChange("old", "tide", 4))
    assert b.hop_blocked("A", "B")
    b.apply(WorldChange("f2", "tide", 6, reopen_waypoints=frozenset({"B"})))
    assert not b.hop_blocked("A", "B")
    b.apply(WorldChange("c1", "collapse", 7, blocked_hops=frozenset({("B", "C")})))
    assert b.hop_blocked("C", "B") and not b.hop_blocked("A", "B")


def test_shortest_prefers_cheapest_and_avoids_blocks():
    _, rep = setup()
    assert rep.shortest("npc_travel", "A", "C")[0] == ["A", "B", "C"]
    rep.blockages.apply(WorldChange("w", "construction", 1, blocked_waypoints=frozenset({"B"})))
    path, cost = rep.shortest("npc_travel", "A", "C")
    assert path == ["A", "D", "C"] and cost == pytest.approx(2 * 200 ** 0.5)
    rep.blockages.apply(WorldChange("w2", "collapse", 2, blocked_hops=frozenset({("D", "C")})))
    with pytest.raises(RepairFailed):
        rep.shortest("npc_travel", "A", "C")


def test_repair_never_uses_unapproved_or_consumer_restricted_hops():
    quest_only = ApprovedRoute("q", ("A", "E", "C"), note("n3"), consumers=frozenset({"quest"}))
    _, rep = setup([quest_only])
    rep.blockages.apply(WorldChange("w", "flood", 1, blocked_waypoints=frozenset({"B", "D"})))
    with pytest.raises(RepairFailed):
        rep.shortest("npc_travel", "A", "C")
    assert rep.shortest("quest", "A", "C")[0] == ["A", "E", "C"]


def test_repair_regrounds_and_fails_closed_on_revoked_signature():
    g, rep = setup()
    prev = g.ground("npc_travel", ["A", "B", "C"])
    rep.blockages.apply(WorldChange("w", "terrain", 1, blocked_waypoints=frozenset({"B"})))
    trig = RepairTrigger("npc", 1, "blocked", "A", "")
    out = rep.repair(trig, prev, PositionFix("npc", 0, 0))
    assert out.plan.waypoints == ("A", "D", "C") and out.plan.route_ids == ("hill", "hill")
    assert out.plan.note_ids == ("n2",)
    g.verifier = lambda payload, sig: False  # key rotated / note revoked
    with pytest.raises(RepairFailed, match="re-grounding"):
        rep.repair(trig, prev, PositionFix("npc", 0, 0))


def test_missing_coordinates_fail_closed():
    g = RouteGrounder(hmac_verifier(KEY))
    g.approve(ApprovedRoute("r", ("A", "Z"), note("n")))
    with pytest.raises(RepairFailed, match="surveyed"):
        RouteRepairer(g, COORDS).shortest("npc_travel", "A", "Z")


def test_point_segment_distance():
    assert point_segment_distance((5, 3, 0), (0, 0, 0), (10, 0, 0)) == pytest.approx(3)
    assert point_segment_distance((-4, 3, 0), (0, 0, 0), (10, 0, 0)) == pytest.approx(5)
    assert point_segment_distance((1, 1, 0), (0, 0, 0), (0, 0, 0)) == pytest.approx(2 ** 0.5)


def _hub_monitor(**kw):
    g, rep = setup()
    mon = RouteMonitor(rep, **kw)
    hub = FrameGPSHub(frozenset({("pc", "modern")}), max_speed_per_frame=50)
    hub.subscribe(mon)
    mon.follow("npc", g.ground("npc_travel", ["A", "B", "C"]))
    return hub, mon, rep


def test_monitor_flags_blocked_hop_ahead_from_gps_frames():
    hub, mon, rep = _hub_monitor()
    hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 1, 0)])
    assert mon.triggers == []
    rep.blockages.apply(WorldChange("c", "collapse", 1, blocked_hops=frozenset({("B", "C")})))
    hub.submit_frame("pc", "modern", 1, [PositionFix("npc", 2, 0)])
    assert [(t.reason, t.from_waypoint) for t in mon.triggers] == [("blocked", "A")]


def test_monitor_advances_waypoints_and_flags_sustained_deviation_only():
    hub, mon, _ = _hub_monitor(corridor=2.0, deviation_frames=3)
    hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 10.2, 0)])
    assert list(mon.remaining("npc")) == ["B", "C"]
    hub.submit_frame("pc", "modern", 1, [PositionFix("npc", 12, 5)])
    hub.submit_frame("pc", "modern", 2, [PositionFix("npc", 12, 0.5)])  # back in corridor resets
    hub.submit_frame("pc", "modern", 3, [PositionFix("npc", 13, 5)])
    hub.submit_frame("pc", "modern", 4, [PositionFix("npc", 14, 5)])
    assert mon.triggers == []
    hub.submit_frame("pc", "modern", 5, [PositionFix("npc", 15, 5)])
    assert [(t.reason, t.from_waypoint, t.frame) for t in mon.triggers] == [("deviated", "B", 5)]


def test_deviated_repair_restarts_from_nearest_open_waypoint():
    g, rep = setup()
    prev = g.ground("npc_travel", ["A", "B", "C"])
    trig = RepairTrigger("npc", 3, "deviated", "A", "")
    out = rep.repair(trig, prev, PositionFix("npc", 9, 9))
    assert out.plan.waypoints == ("D", "C")


def test_untracked_entities_ignored_and_goal_reached_is_quiet():
    hub, mon, _ = _hub_monitor()
    hub.submit_frame("pc", "modern", 0, [PositionFix("other", 50, 50), PositionFix("npc", 20, 0)])
    assert mon.triggers == []


@pytest.mark.parametrize("bad", [True, -1, float("nan"), 1.5, 2**64])
def test_world_change_rejects_invalid_frame_order_evidence(bad):
    with pytest.raises(ValueError, match="world change frame"):
        WorldChange("change", "flood", bad)


@pytest.mark.parametrize("bad", ["", "x" * 129, "change\\nforged", None])
def test_world_change_rejects_ambiguous_change_ids(bad):
    with pytest.raises(ValueError, match="change_id"):
        WorldChange(bad, "flood", 1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "2"])
def test_route_monitor_rejects_invalid_corridor_thresholds(bad):
    _, repairer = setup()
    with pytest.raises(ValueError, match="corridor"):
        RouteMonitor(repairer, corridor=bad)
    with pytest.raises(ValueError, match="arrive_radius"):
        RouteMonitor(repairer, arrive_radius=bad)


@pytest.mark.parametrize("bad", [0, True, -1, 10001, 1.5])
def test_route_monitor_rejects_invalid_deviation_frame_thresholds(bad):
    _, repairer = setup()
    with pytest.raises(ValueError, match="deviation_frames"):
        RouteMonitor(repairer, deviation_frames=bad)


def test_world_change_topology_evidence_is_bounded_and_unambiguous(monkeypatch):
    from skeleton.frontier_nav import route_repair as mod

    bad = [
        {"blocked_waypoints": {"A"}},
        {"blocked_waypoints": frozenset({"bad\u202ename"})},
        {"blocked_hops": frozenset({("A", "A")})},
        {"blocked_hops": frozenset({("A", "bad\nnode")})},
        {"blocked_hops": frozenset({("A",)})},
        {"blocked_hops": frozenset({("A", "B")}),
         "reopen_hops": frozenset({("B", "A")})},
        {"blocked_waypoints": frozenset({"A"}),
         "reopen_waypoints": frozenset({"A"})},
    ]
    for kwargs in bad:
        with pytest.raises(ValueError, match="topology"):
            WorldChange("bad", "flood", 1, **kwargs)

    monkeypatch.setattr(mod, "MAX_WORLD_CHANGE_WAYPOINTS", 1)
    with pytest.raises(ValueError, match="topology"):
        WorldChange("many", "flood", 1, blocked_waypoints=frozenset({"A", "B"}))
    monkeypatch.setattr(mod, "MAX_WORLD_CHANGES", 1)
    blockages = Blockages()
    assert blockages.apply(WorldChange("first", "flood", 1))
    assert not blockages.apply(WorldChange("first", "flood", 1))
    with pytest.raises(ValueError, match="history exceeds capacity"):
        blockages.apply(WorldChange("second", "flood", 2))
    assert blockages.last_frame == 1


def test_reused_world_change_identity_cannot_silently_drop_new_blockage():
    blockages = Blockages()
    original = WorldChange("same-id", "flood", 10, blocked_waypoints=frozenset({"B"}))
    assert blockages.apply(original)
    assert not blockages.apply(original)
    with pytest.raises(ValueError, match="conflicting world change identity"):
        blockages.apply(WorldChange("same-id", "flood", 10,
                                   blocked_waypoints=frozenset({"C"})))
    assert blockages.hop_blocked("A", "B")
    assert not blockages.hop_blocked("A", "C")
    assert blockages.last_frame == 10
