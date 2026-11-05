import asyncio

from skeleton.forge.ai_builder import (
    AiBuilderEngine, ModelPlanner, PlanLedger, clarifying_questions, grant_providers,
    plan_provenance, router_planner_hook,
)
from skeleton.forge.game_design_spec import GOLDEN_BRIEFS, compile_brief, spec_digest
from skeleton.gameforge.batch_b038 import GenerationProvenance, ProvenanceLedger

from .fakes import FakeRouter, gate_and_issuer

BRIEF = GOLDEN_BRIEFS[1]["brief"]
B038_KEYS = {"schema", "artifact_id", "artifact_digest", "model", "provider", "input_digest",
             "parameters", "sources", "transformations", "evals", "steps"}


def planner(grant=("alpha",), chain=("alpha",)):
    gate, issuer = gate_and_issuer()
    return ModelPlanner(FakeRouter(chain=chain), gate=gate, cap=grant_providers(issuer, grant))


def test_model_plan_provenance_is_b038_shaped():
    out = asyncio.run(planner().plan(BRIEF))
    prov = plan_provenance(out)
    assert isinstance(prov, GenerationProvenance)
    rec = prov.to_record()
    assert set(rec) == B038_KEYS
    assert rec["provider"] == "alpha" and rec["artifact_digest"] == spec_digest(out.spec)
    assert [t["name"] for t in rec["transformations"]] == ["compile_brief", "plan_guard"]
    assert rec["parameters"]["route_receipt_digest"] == out.receipt.receipt_digest()


def test_denied_plan_still_ledgered():
    out = asyncio.run(planner(grant=("nobody",)).plan(BRIEF))
    ledger = PlanLedger()
    h = ledger.record(out)
    assert isinstance(ledger, ProvenanceLedger) and ledger.head == h
    assert ProvenanceLedger.verify(ledger.entries())
    rec = ledger.entries()[0]["record"]
    assert rec["provider"] == "compiler" and rec["parameters"]["route_status"] == "denied"
    assert rec["artifact_digest"] == spec_digest(compile_brief(BRIEF))


def test_engine_plan_produces_verified_forge_data():
    eng = AiBuilderEngine(planner())
    res = asyncio.run(eng.plan(BRIEF))
    d = res.as_dict()
    assert d["source"] == "model" and d["receipt"]["status"] == "ok"
    fd = res.forge_data
    assert fd["target"] == "json" and fd["files"] and fd["spec_id"] == res.outcome.spec["spec_id"]
    assert eng.ledger.head == res.provenance_hash


def test_engine_build_passes_committed_spec_as_planner():
    seen = {}

    def fake_build(brief, *, era, planner, **kw):
        seen["spec"] = planner(compile_brief(brief))
        seen["kw"] = kw
        return {"status": "ok"}

    eng = AiBuilderEngine(planner(), build_fn=fake_build)
    res = asyncio.run(eng.build(BRIEF, target="godot"))
    assert res.build == {"status": "ok"} and seen["kw"] == {"target": "godot"}
    assert seen["spec"]["title"] == "Ledge Runner"


def test_sync_hook_and_clarify():
    outs = []
    hook = router_planner_hook(planner(), on_outcome=outs.append)
    spec = hook(compile_brief(BRIEF))
    assert spec["title"] == "Ledge Runner" and outs[0].source == "model"
    assert clarifying_questions(BRIEF, spec) == []
    qs = clarifying_questions("something about ghosts", compile_brief("something about ghosts"))
    assert [q["field"] for q in qs] == ["genre", "fantasy", "core_loop"]
