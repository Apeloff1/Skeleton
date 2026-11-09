import pytest
from skeleton.ai.project_memory import *
def f(i,**kw):return ProjectFact(i,kw.get("tenant","t"),kw.get("project","p"),kw.get("trust","verified"),"v","source",kw.get("supersedes"))
def test_project_tenant_trust_boundaries_are_enforced():
 m=ProjectMemory("t","p","verified")
 for x in (f("1",tenant="x"),f("1",project="x"),f("1",trust="untrusted")):
  with pytest.raises(PermissionError):m.add(x)
 with pytest.raises(PermissionError):m.visible("t","other","verified")
def test_source_and_supersession_lineage_preserved():
 m=ProjectMemory("t","p","verified").add(f("1"));m=m.add(f("2",supersedes="1"))
 assert [x.fact_id for x in m.visible("t","p","verified")]==["2"] and m.facts[1].source_id=="source"
def test_missing_supersession_target_fails_closed():
 with pytest.raises(ValueError):ProjectMemory("t","p","verified").add(f("2",supersedes="missing"))

def test_supersession_fork_rejected():
 import pytest
 m=ProjectMemory("t","p","trusted").add(ProjectFact("a","t","p","trusted","v","s"))
 m=m.add(ProjectFact("b","t","p","trusted","v2","s","a"))
 with pytest.raises(ValueError):m.add(ProjectFact("c","t","p","trusted","v3","s","a"))
