import hashlib
import hmac

import pytest

from skeleton.frontier_nav import (
    ApprovedRoute,
    DesignNote,
    FrameGPSHub,
    GPSRejected,
    GroundingRejected,
    PositionFix,
    RouteGrounder,
    hmac_verifier,
)

KEY = b"test-key"


def _hub(**kw):
    return FrameGPSHub(lanes=frozenset({("snes", "16bit"), ("ps2", "3d")}), **kw)


def test_per_frame_hooks_and_proof_chain():
    hub = _hub()
    seen = []
    hub.subscribe(seen.append)
    ups = [
        hub.submit_frame("snes", "16bit", f, [PositionFix("npc", f, 0)])
        for f in range(5)
    ]
    assert [u.frame for u in seen] == list(range(5))
    assert hub.position("snes", "16bit", "npc").x == 4
    assert FrameGPSHub.verify_chain(hub.proofs("snes", "16bit"), ups)
    tampered = [
        ups[0],
        ups[1].__class__(**{**ups[1].__dict__, "fixes": (PositionFix("npc", 9, 9),)}),
    ]
    assert not FrameGPSHub.verify_chain(hub.proofs("snes", "16bit")[:2], tampered)


def test_lanes_isolated_and_rejections():
    hub = _hub(max_speed_per_frame=2.0)
    hub.submit_frame("snes", "16bit", 0, [PositionFix("a", 0, 0)])
    hub.submit_frame("ps2", "3d", 0, [PositionFix("a", 50, 0)])
    with pytest.raises(GPSRejected):
        hub.submit_frame("snes", "16bit", 0, [PositionFix("a", 1, 0)])
    with pytest.raises(GPSRejected):
        hub.submit_frame("n64", "3d", 0, [])
    with pytest.raises(GPSRejected):
        hub.submit_frame("snes", "16bit", 1, [PositionFix("a", 10, 0)])
    with pytest.raises(GPSRejected):
        hub.submit_frame("snes", "16bit", 1, [PositionFix("a", float("nan"), 0)])
    with pytest.raises(GPSRejected):
        hub.submit_frame(
            "snes", "16bit", 1, [PositionFix("b", 0, 0), PositionFix("b", 1, 0)]
        )
    hub.submit_frame("snes", "16bit", 3, [PositionFix("a", 5, 0)])  # 3 frames * 2 units


def test_unsubscribe():
    hub = _hub()
    seen = []
    off = hub.subscribe(seen.append)
    off()
    hub.submit_frame("snes", "16bit", 0, [])
    assert seen == []


def _note(nid, body, key=KEY):
    sig = hmac.new(key, f"{nid}\n{body}".encode(), hashlib.sha256).hexdigest()
    return DesignNote(nid, body, sig)


def test_grounding_accepts_only_signed_approved_hops():
    g = RouteGrounder(hmac_verifier(KEY))
    g.approve(ApprovedRoute("r1", ("town", "bridge", "cave"), _note("n1", "road")))
    g.approve(
        ApprovedRoute(
            "r2",
            ("cave", "lair"),
            _note("n2", "dragon"),
            frozenset({"dragon_map"}),
            False,
        )
    )
    plan = g.ground("npc_travel", ["cave", "bridge", "town"])
    assert plan.route_ids == ("r1", "r1") and plan.note_ids == ("n1",)
    assert g.ground("dragon_map", ["town", "bridge", "cave", "lair"]).note_ids == (
        "n1",
        "n2",
    )
    for consumer, wps in [
        ("quest", ["cave", "lair"]),
        ("dragon_map", ["lair", "cave"]),
        ("jeeves_map", ["town", "cave"]),
        ("hacker", ["town", "bridge"]),
        ("quest", ["town"]),
    ]:
        with pytest.raises(GroundingRejected):
            g.ground(consumer, wps)


def test_bad_signature_and_duplicate_rejected():
    g = RouteGrounder(hmac_verifier(KEY))
    with pytest.raises(GroundingRejected):
        g.approve(ApprovedRoute("x", ("a", "b"), _note("n", "b", key=b"other")))
    g.approve(ApprovedRoute("r", ("a", "b"), _note("n", "b")))
    with pytest.raises(GroundingRejected):
        g.approve(ApprovedRoute("r", ("a", "c"), _note("n", "c")))
    with pytest.raises(GroundingRejected):
        g.approve(ApprovedRoute("s", ("a",), _note("m", "c")))
