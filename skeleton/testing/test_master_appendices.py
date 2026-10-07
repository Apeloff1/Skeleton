from __future__ import annotations
import hashlib,pytest
from skeleton.automation.master_appendices import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def test_reference_is_bound_to_canonical_machine_digest():
 r=AppendixReference("REF.PLAN","machine/ai_master_plan.json",S("plan"),"master plan");i=ReferenceIndex((r,),());assert i.stale_references({"machine/ai_master_plan.json":S("plan")})==()
def test_stale_appendix_cannot_silently_override_canonical_source():
 r=AppendixReference("REF.PLAN","machine/ai_master_plan.json",S("old"),"master plan");assert ReferenceIndex((r,),()).stale_references({"machine/ai_master_plan.json":S("new")})==("REF.PLAN",)
def test_normative_terms_have_owner_and_version():
 t=TermDefinition("TERM.MATURITY","maturity","evidence-derived state","OWNER.GOV",2);assert ReferenceIndex((),(t,)).resolve_term("TERM.MATURITY").version==2
def test_duplicate_term_name_rejected_even_with_different_ids():
 a=TermDefinition("TERM.A","Maturity","a","OWNER.A",1);b=TermDefinition("TERM.B","maturity","b","OWNER.B",1)
 with pytest.raises(AppendixError,match="duplicate normative term"):ReferenceIndex((),(a,b))
def test_duplicate_reference_id_rejected():
 a=AppendixReference("REF.X","a",S("a"),"a");b=AppendixReference("REF.X","b",S("b"),"b")
 with pytest.raises(AppendixError,match="duplicate appendix"):ReferenceIndex((a,b),())

def test_appendix_paths_are_repository_relative():
 with pytest.raises(AppendixError,match="repository relative"):AppendixReference("REF.X","../machine/x.json",S("x"),"x")
 with pytest.raises(AppendixError,match="repository relative"):AppendixReference("REF.X","/machine/x.json",S("x"),"x")
def test_term_version_rejects_boolean_alias():
 with pytest.raises(AppendixError,match="invalid"):TermDefinition("TERM.X","x","definition","OWNER.X",True)
def test_registry_requires_typed_tuples():
 with pytest.raises(AppendixError,match="typed tuples"):ReferenceIndex([],())
def test_digest_snapshot_is_runtime_validated():
 r=AppendixReference("REF.X","machine/x.json",S("x"),"x")
 with pytest.raises(AppendixError,match="sha256"):ReferenceIndex((r,),()).stale_references({"machine/x.json":"not-a-digest"})
