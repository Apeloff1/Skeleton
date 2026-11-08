import asyncio

import pytest

from skeleton.forge.ai_builder import AiBuilderEngine, ModelPlanner, grant_providers
from skeleton.forge.ai_builder.validate import Thresholds, ValidatingEngine, plan_qa_hook, score_plan
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS

from .fakes import FakeRouter, gate_and_issuer
from .plan_fixtures import good_plan


def test_clean_plan_accepts_full_score():
    v = score_plan(good_plan())
    assert v.verdict == "accept" and v.score == pytest.approx(1.0) and not v.problems


def test_schema_error_regenerates():
    p = good_plan(); del p["player"]
    assert score_plan(p).verdict == "regenerate"
    assert score_plan("junk").verdict == "regenerate"


def test_playability_error_repairs():
    p = good_plan(); p["triggers"].append({"id": "t3", "on": "music", "emits": ["spawn"]})
    v = score_plan(p)
    assert v.verdict == "repair" and v.by_rule["logic_loop"] == 0.0 and v.score == pytest.approx(0.9)


def test_many_failures_drop_below_repair_threshold():
    p = good_plan()
    p["levels"][0]["scene"] = "void"; p["start_level"] = "nope"; p["encounters"][0]["system"] = "x"
    v = score_plan(p)  # references + reachability + winnable(e?) lost
    assert v.score < 0.85
    assert score_plan(p, Thresholds(accept=0.9, repair=0.8)).verdict == "regenerate"


def test_warnings_only_can_still_accept_or_repair_by_threshold():
    p = good_plan(); p["assets"].append({"id": "spare", "kind": "sfx"})
    v = score_plan(p)
    assert v.verdict == "accept" and v.score == pytest.approx(1 - 0.25 * 0.2)
    assert score_plan(p, Thresholds(accept=0.99)).verdict == "repair"


def test_thresholds_validated_and_as_dict():
    with pytest.raises(ValueError):
        Thresholds(accept=0.4, repair=0.6)
    d = score_plan(good_plan()).as_dict()
    assert set(d) == {"verdict", "score", "by_rule", "problems"}


def test_qa_hook_shapes():
    bad = good_plan(); bad["triggers"].append({"id": "t3", "on": "music", "emits": ["spawn"]})
    r = plan_qa_hook()({"game_plan": bad})
    assert r["verdict"] == "repair" and r["repair_requested"] is True and r["issues"]
    assert plan_qa_hook(good_plan())({})["repair_requested"] is False
    assert plan_qa_hook()({})["skipped"] == "no game_plan"
    regen = plan_qa_hook()({"game_plan": {}})
    assert regen["verdict"] == "regenerate" and regen["repair_requested"] is False


def _planner():
    gate, issuer = gate_and_issuer()
    return ModelPlanner(FakeRouter(chain=("alpha",)), gate=gate, cap=grant_providers(issuer, ["alpha"]))


def _capture():
    seen = {}

    def build(brief, *, era, planner, **kw):
        seen.update(kw)
        return {"status": "ok"}
    return seen, build


def test_engine_default_unchanged_and_opt_in_adds_qa():
    brief = GOLDEN_BRIEFS[1]["brief"]
    base_seen, b1 = _capture()
    asyncio.run(AiBuilderEngine(_planner(), build_fn=b1).build(brief))
    off_seen, b2 = _capture()
    asyncio.run(ValidatingEngine(_planner(), build_fn=b2).build(brief))
    assert base_seen == off_seen == {}
    on_seen, b3 = _capture()
    eng = ValidatingEngine(_planner(), build_fn=b3, validate=True)
    asyncio.run(eng.build(brief))
    assert callable(on_seen["qa"]) and on_seen["qa"]({"game_plan": good_plan()})["verdict"] == "accept"
    mine = lambda b: {}
    kept, b4 = _capture()
    asyncio.run(ValidatingEngine(_planner(), build_fn=b4, validate=True).build(brief, qa=mine))
    assert kept["qa"] is mine
    assert eng.score(good_plan()).verdict == "accept"
