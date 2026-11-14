"""GF-L / GF-P2-01, GF-P2-06: closed-loop nav cognition with verify + rollback."""

import hashlib
import hmac
from dataclasses import dataclass, field

import pytest

from skeleton.frontier_nav.cognition_loop import (
    CognitionHalt,
    CognitionLoop,
    Prediction,
    RuntimeBindingAdapter,
    SpeculationPolicy,
)
from skeleton.frontier_nav.gps import FrameGPSHub, PositionFix
from skeleton.frontier_nav.route_grounding import (
    ApprovedRoute,
    DesignNote,
    RouteGrounder,
    hmac_verifier,
)
from skeleton.frontier_nav.route_repair import RouteMonitor, RouteRepairer, WorldChange

KEY = b"k" * 32
COORDS = {"A": (0.0, 0.0, 0.0), "B": (10.0, 0.0, 0.0), "C": (20.0, 0.0, 0.0),
          "D": (10.0, 10.0, 0.0)}


def note(nid):
    return DesignNote(nid, "ok", hmac.new(KEY, f"{nid}\nok".encode(), hashlib.sha256).hexdigest())


@dataclass
class FakeBinding:  # duck-typed GF-A RuntimeBinding (#4595)
    era: str = "modern"
    fps: int = 60
    binding_id: str = "b" * 64


@dataclass
class Actuator:
    issued: list = field(default_factory=list)
    cancelled: list = field(default_factory=list)

    def step(self, entity_id, target, frame):
        cid = f"cmd{len(self.issued)}"
        self.issued.append((cid, entity_id, target, frame))
        return cid

    def cancel(self, command_id):
        self.cancelled.append(command_id)


def oracle(conf=0.9, lat=10.0):
    def predict(fix, plan, frame):
        # next waypoint not yet reached along the plan
        wps = plan.waypoints
        nxt = next((w for w in wps if (fix.x, fix.y, fix.z) != COORDS[w] and
                    wps.index(w) > 0), wps[-1])
        return Prediction(fix.entity_id, nxt, conf, lat)
    return predict


def build(conf=0.9, lat=10.0, binding=None, **policy):
    g = RouteGrounder(hmac_verifier(KEY))
    g.approve(ApprovedRoute("main", ("A", "B", "C"), note("n1")))
    g.approve(ApprovedRoute("hill", ("A", "D", "C"), note("n2")))
    rep = RouteRepairer(g, COORDS)
    mon = RouteMonitor(rep)
    mon.follow("npc", g.ground("npc_travel", ["A", "B", "C"]))
    act = Actuator()
    view = RuntimeBindingAdapter().view(binding or FakeBinding())
    loop = CognitionLoop(mon, act, oracle(conf, lat), view, "pc",
                         SpeculationPolicy(**policy))
    hub = FrameGPSHub(frozenset({("pc", "modern"), ("pc", "medieval")}), max_speed_per_frame=50)
    return hub, loop, act, rep


def phases(events):
    return [e.phase for e in events]


def test_adapter_rejects_bad_bindings_and_unactionable_claims():
    ad = RuntimeBindingAdapter()
    with pytest.raises(CognitionHalt):
        ad.view(object())
    with pytest.raises(CognitionHalt):
        ad.view(FakeBinding(fps=0))
    with pytest.raises(CognitionHalt, match="claim"):
        RuntimeBindingAdapter(lambda b: {"claim": "draft"}).view(FakeBinding())
    v = RuntimeBindingAdapter(lambda b: {"claim": "bound_pending_native_render_qa"}).view(FakeBinding())
    assert v.era == "modern" and v.fps == 60


def test_perceive_act_verify_happy_path():
    hub, loop, act, _ = build()
    ev = loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    assert phases(ev) == ["perceive", "act"] and act.issued[0][2] == "B"
    ev = loop.tick(hub.submit_frame("pc", "modern", 1, [PositionFix("npc", 4, 0)]))
    assert phases(ev) == ["perceive", "verify", "act"]
    assert act.cancelled == []


def test_no_progress_rolls_back_and_holds():
    hub, loop, act, _ = build(verify_within_frames=2)
    loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    loop.tick(hub.submit_frame("pc", "modern", 1, [PositionFix("npc", 0, 0.5)]))
    ev = loop.tick(hub.submit_frame("pc", "modern", 2, [PositionFix("npc", 0, 0.5)]))
    assert "rollback" in phases(ev) and act.cancelled == ["cmd0"]
    ev = loop.tick(hub.submit_frame("pc", "modern", 3, [PositionFix("npc", 1, 0)]))
    assert "act" not in phases(ev)  # held until authority resumes
    loop.resume("npc")
    ev = loop.tick(hub.submit_frame("pc", "modern", 4, [PositionFix("npc", 1, 0)]))
    assert "act" in phases(ev)


@pytest.mark.parametrize("conf,lat", [(0.3, 10.0), (0.9, 500.0), (float("nan"), 1.0)])
def test_low_confidence_or_stale_prediction_abstains(conf, lat):
    hub, loop, act, _ = build(conf=conf, lat=lat)
    ev = loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    assert phases(ev) == ["perceive", "abstain"] and act.issued == []


def test_blocked_route_cancels_pending_step_and_repairs():
    hub, loop, act, rep = build()
    loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    rep.blockages.apply(WorldChange("f", "flood", 1, blocked_waypoints=frozenset({"B"})))
    ev = loop.tick(hub.submit_frame("pc", "modern", 1, [PositionFix("npc", 0, 0.1)]))
    assert act.cancelled == ["cmd0"] and phases(ev)[-2:] == ["plan", "act"]
    plan_ev = next(e for e in ev if e.phase == "plan")
    assert "A->D->C" in plan_ev.detail and "hill" in plan_ev.detail
    assert act.issued[-1][2] == "D"


def test_unrepairable_block_holds_entity():
    hub, loop, act, rep = build()
    rep.blockages.apply(WorldChange("x", "collapse", 0,
                                    blocked_waypoints=frozenset({"B", "D"})))
    ev = loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    assert phases(ev) == ["perceive", "hold"] and act.issued == []


def test_era_mismatch_and_replay_halt():
    hub, loop, _, _ = build()
    with pytest.raises(CognitionHalt, match="not bound"):
        loop.tick(hub.submit_frame("pc", "medieval", 0, [PositionFix("npc", 0, 0)]))
    upd = hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)])
    loop.tick(upd)
    with pytest.raises(CognitionHalt, match="replayed"):
        loop.tick(upd)


def test_prediction_for_wrong_target_is_not_issued():
    hub, loop, act, _ = build()
    loop.predictor = lambda fix, plan, frame: Prediction("npc", "C", 0.99, 1.0)
    ev = loop.tick(hub.submit_frame("pc", "modern", 0, [PositionFix("npc", 0, 0)]))
    assert phases(ev) == ["perceive", "abstain"] and act.issued == []


def test_adapter_accepts_real_gf_a_runtime_binding():
    gfa = pytest.importorskip("skeleton.jeeves.game_frontier_runtime_binding")
    binding = gfa.RuntimeBinding("c" * 64, "modern", 30, "op", "s" * 64, (), (),
                                 {"a.gd": "x"}, 1)
    view = RuntimeBindingAdapter(gfa.binding_ui_status).view(binding)
    assert view.binding_id == binding.binding_id and view.claim == "bound_pending_native_render_qa"
