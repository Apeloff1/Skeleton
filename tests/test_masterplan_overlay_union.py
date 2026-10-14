from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_masterplan_overlay_union.py"

def _module():
    spec=importlib.util.spec_from_file_location("overlay_union",SCRIPT)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _fixture(tmp_path: Path):
    machine=tmp_path/"machine"; docs=tmp_path/"docs/plan"; scripts=tmp_path/"scripts"; tests=tmp_path/"tests"
    machine.mkdir(parents=True); docs.mkdir(parents=True); scripts.mkdir(); tests.mkdir()
    authority="machine/example.json"; companion="tests/example.py"
    (tmp_path/authority).write_text(json.dumps({"levels":[1,2]}),encoding="utf-8")
    (tmp_path/companion).write_text("pass\n",encoding="utf-8")
    (machine/"ai_master_plan.json").write_text(json.dumps({"plan_version":"2.5.0","authority":authority}),encoding="utf-8")
    (docs/"MASTER_PLAN.md").write_text(authority,encoding="utf-8")
    (docs/"MASTER_INDEX.md").write_text("",encoding="utf-8")
    registry={
      "minimum_plan_version":"2.5.0",
      "canonical_plan":"machine/ai_master_plan.json",
      "human_plan":"docs/plan/MASTER_PLAN.md",
      "human_index":"docs/plan/MASTER_INDEX.md",
      "overlays":[{"id":"example","authority":authority,"min_bytes":2,"semantic_checks":[{"path":"levels","kind":"length","expected":2}],"companions":[companion]}],
    }
    rp=machine/"masterplan_overlay_registry.json"
    rp.write_text(json.dumps(registry),encoding="utf-8")
    return rp,authority,companion

def test_masterplan_overlay_union_is_gapless():
    assert _module().validate()==[]

def test_semantic_cardinalities_are_exact():
    m=_module()
    assert m._check_semantics("x",{"levels":[1,2]},[{"path":"levels","kind":"length","expected":2}])==[]
    assert m._check_semantics("x",{"levels":[1]},[{"path":"levels","kind":"length","expected":2}])

def test_zero_byte_authority_fails_closed(tmp_path,monkeypatch):
    m=_module(); rp,authority,_=_fixture(tmp_path)
    monkeypatch.setattr(m,"MANDATORY",{"example"})
    (tmp_path/authority).write_text("",encoding="utf-8")
    assert any("too small/empty" in e for e in m.validate(tmp_path,rp))

def test_missing_companion_fails_closed(tmp_path,monkeypatch):
    m=_module(); rp,_,companion=_fixture(tmp_path)
    monkeypatch.setattr(m,"MANDATORY",{"example"})
    (tmp_path/companion).unlink()
    assert any("missing companion" in e for e in m.validate(tmp_path,rp))

def test_plan_version_rollback_fails_closed(tmp_path,monkeypatch):
    m=_module(); rp,_,_=_fixture(tmp_path)
    monkeypatch.setattr(m,"MANDATORY",{"example"})
    (tmp_path/"machine/ai_master_plan.json").write_text(json.dumps({"plan_version":"2.4.9","authority":"machine/example.json"}),encoding="utf-8")
    assert any("plan_version regressed" in e for e in m.validate(tmp_path,rp))

def test_truncated_semantic_authority_fails_closed(tmp_path,monkeypatch):
    m=_module(); rp,authority,_=_fixture(tmp_path)
    monkeypatch.setattr(m,"MANDATORY",{"example"})
    (tmp_path/authority).write_text(json.dumps({"levels":[1]}),encoding="utf-8")
    assert any("length 1 != 2" in e for e in m.validate(tmp_path,rp))
