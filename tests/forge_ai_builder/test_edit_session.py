import asyncio
import json

import pytest

from skeleton.forge.ai_builder import ModelPlanner, grant_providers
from skeleton.forge.ai_builder.edit import EditPlanner, EditSession, ProjectHistoryLike, ProjectSaverLike
from skeleton.frontier.runtime.model_router_contract import RouteStatus
from skeleton.gameforge.batch_b038 import GenerationProvenance, ProvenanceLedger

from .fakes import FakeRouter, gate_and_issuer
from .history_fake import FakeHistory
from .plan_fixtures import good_plan

SCHEMA = "skeleton.forge.ai_builder.plan_edit.v1"


def run(c):
    return asyncio.run(c)


def editor(reply=None, grant=("alpha",)):
    gate, issuer = gate_and_issuer()
    return EditPlanner(FakeRouter(chain=("alpha",), reply=reply), gate=gate, cap=grant_providers(issuer, grant))


def model_reply(ops):
    return lambda pid: json.dumps({"schema": SCHEMA, "ops": ops})


def test_model_diff_used_when_granted():
    ed = editor(model_reply([{"op": "change", "path": ["player", "hp"], "value": 150}]))
    p = run(ed.propose("buff the hero", good_plan()))
    assert p.source == "model" and p.receipt.status == RouteStatus.OK
    assert p.diff.ops[0].path == ("player", "hp")


def test_denied_falls_back_to_rules_with_receipt():
    ed = editor(model_reply([]), grant=("other",))
    p = run(ed.propose("set player hp to 120", good_plan()))
    assert p.source == "rules" and p.receipt.status == RouteStatus.DENIED
    assert p.fallback_reason == "route:denied" and ed._router.invoked == []


def test_bad_model_output_falls_back_and_unparsed():
    ed = editor(lambda pid: "nope")
    p = run(ed.propose("set title to Z", good_plan()))
    assert p.source == "rules" and p.fallback_reason.startswith("parse:")
    p = run(ed.propose("make it spooky", good_plan()))
    assert p.source == "none" and p.diff is None


def test_from_planner_shares_gate_and_token():
    gate, issuer = gate_and_issuer()
    mp = ModelPlanner(FakeRouter(), gate=gate, cap=grant_providers(issuer, ["alpha"]))
    ep = EditPlanner.from_planner(mp)
    assert ep._gate is gate and ep._cap == mp._cap and ep._router is mp._router
    with pytest.raises(ValueError):
        EditPlanner(FakeRouter(), gate=None, cap=None)


def test_protocol_satisfied_by_fake():
    h = FakeHistory()
    assert isinstance(h, ProjectHistoryLike) and isinstance(h.saver, ProjectSaverLike)


def test_accepted_edit_recorded_with_inverse_provenance_and_history():
    h = FakeHistory()
    s = EditSession(good_plan(), editor(grant=("none",)), history=h, project_id="p1", genre="platformer")
    r = run(s.edit("set player hp to 120"))
    assert r.status == "accepted" and s.plan["player"]["hp"] == 120
    rec = r.record
    assert rec.inverse.ops[0].value == 100 and isinstance(rec.provenance, GenerationProvenance)
    assert rec.provenance.to_record()["provider"] == "rules"
    assert s.ledger.head and ProvenanceLedger.verify(s.ledger.entries())
    labels = [v.label for v in h.versions("p1")]
    assert labels == ["edit-base", "edit-1"]
    saved = h.saver.load("p1")
    assert json.loads(saved.files["game_plan.json"])["player"]["hp"] == 120
    assert saved.sections["ai_builder_edit"]["inverse"]["ops"][0]["value"] == 100


def test_regenerate_verdict_rejects_and_keeps_old_plan():
    h = FakeHistory()
    ed = editor(model_reply([{"op": "remove", "path": ["player"]}]))
    s = EditSession(good_plan(), ed, history=h, project_id="p1")
    r = run(s.edit("drop the hero"))  # missing player -> schema error
    assert r.status == "rejected" and r.verdict.verdict == "regenerate"
    assert s.plan == good_plan() and not s.undo_stack and len(h.versions("p1")) == 1


def test_repair_verdict_applied_and_reported():
    s = EditSession(good_plan(), editor(grant=("none",)))
    r = run(s.edit("remove exit from l2 to l3"))  # goal unreachable
    assert r.status == "repair" and "no goal level is reachable from start" in r.issues
    assert s.plan["levels"][1]["exits"] == ["l1"] and len(s.undo_stack) == 1


def test_invalid_and_unparsed_leave_plan():
    s = EditSession(good_plan(), editor(grant=("none",)))
    assert run(s.edit("remove encounter zz")).status == "invalid"
    assert run(s.edit("make it better")).status == "unparsed"
    assert s.plan == good_plan()


def test_undo_redo_with_history_rollback():
    h = FakeHistory()
    s = EditSession(good_plan(), editor(grant=("none",)), history=h, project_id="p1")
    run(s.edit("set player hp to 120"))
    run(s.edit("set title to Tide"))
    assert s.undo().seq == 2 and s.plan["title"] == "Ledge Runner"
    assert s.undo().seq == 1 and s.plan == good_plan()
    assert s.undo() is None
    assert json.loads(h.saver.load("p1").files["game_plan.json"]) == good_plan()
    assert s.redo().seq == 1 and s.plan["player"]["hp"] == 120
    assert json.loads(h.saver.load("p1").files["game_plan.json"])["player"]["hp"] == 120
    run(s.edit("set player dps to 11"))
    assert s.redo() is None  # new edit clears redo
    assert [v.label for v in h.versions("p1")][-1] == "edit-3"


def test_history_requires_project_id():
    with pytest.raises(ValueError):
        EditSession(good_plan(), editor(), history=FakeHistory())
