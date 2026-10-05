from __future__ import annotations
import pytest
from datetime import datetime,timezone
import hashlib
from skeleton.automation.backlog_control import *
def src(i="GAP.1",kind=SourceKind.GAP):return BacklogSource(i,kind,"masterplan gap requires closure")
def item(i,title="Implement closure",rule="tests and evidence pass",sources=None,state=BacklogState.OPEN):return BacklogItem(i,title,"ai-builder",rule,tuple(sources or (src(),)),state)
def proof(x,eid="EVID.1"):
 return ClosureEvidence(eid,x.item_id,x.digest,datetime(2026,10,5,14,0,tzinfo=timezone.utc),hashlib.sha256(b"artifact").hexdigest())
def test_item_requires_source_provenance():
 with pytest.raises(BacklogError,match="source provenance"):item("ITEM.1",sources=())
def test_stable_identity_is_immutable():
 r=BacklogRegistry();r.add(item("ITEM.1"))
 with pytest.raises(BacklogError,match="identity is immutable"):r.add(item("ITEM.1",title="Changed"))
def test_duplicate_detection_is_normalized_and_deterministic():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2",title="  IMPLEMENT   CLOSURE ",rule="TESTS AND EVIDENCE PASS",sources=(src("RISK.2",SourceKind.RISK),)))
 assert r.duplicates("ITEM.1")==("ITEM.2",)
def test_dedup_preserves_both_provenance_sources():
 r=BacklogRegistry();a=item("ITEM.1");b=item("ITEM.2",sources=(src("RISK.2",SourceKind.RISK),));r.add(a);r.add(b)
 d=r.deduplicate("ITEM.1","ITEM.2","DISP.1","same closure semantics")
 assert d.target_item_id=="ITEM.1";assert r._items["ITEM.2"].state is BacklogState.RETIRED
 assert {(s.kind,s.source_id) for s in r._items["ITEM.1"].sources}=={(SourceKind.GAP,"GAP.1"),(SourceKind.RISK,"RISK.2")}
def test_nonduplicate_cannot_be_retired_as_duplicate():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2",title="Different"))
 with pytest.raises(BacklogError,match="not deterministic duplicates"):r.deduplicate("ITEM.1","ITEM.2","DISP.1","no")
def test_unknown_dependency_rejected():
 r=BacklogRegistry();r.add(item("ITEM.1"))
 with pytest.raises(BacklogError,match="unknown item"):r.add_dependency(BacklogDependency("DEP.1","ITEM.1","ITEM.MISSING"))
def test_dependency_cycle_rejected():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2"));r.add_dependency(BacklogDependency("DEP.1","ITEM.2","ITEM.1"))
 with pytest.raises(BacklogError,match="cycle"):r.add_dependency(BacklogDependency("DEP.2","ITEM.1","ITEM.2"))
def test_unsatisfied_dependency_blocks_and_upstream_closure_revalidates():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2"));r.add_dependency(BacklogDependency("DEP.1","ITEM.2","ITEM.1"))
 assert r.reconcile("ITEM.2").state is BacklogState.BLOCKED
 up=r.reconcile("ITEM.1");assert r.close("ITEM.1",proof(up)).state is BacklogState.CLOSED
 assert r.revalidate_dependents("ITEM.1")[0].state is BacklogState.READY
def test_blocked_item_cannot_close():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2"));r.add_dependency(BacklogDependency("DEP.1","ITEM.2","ITEM.1"))
 with pytest.raises(BacklogError,match="blocked item"):r.close("ITEM.2",proof(r._items["ITEM.2"]))
def test_closure_requires_evidence():
 r=BacklogRegistry();r.add(item("ITEM.1"))
 with pytest.raises(BacklogError,match="requires evidence"):r.close("ITEM.1",False)
def test_item_without_dependencies_becomes_ready():
 r=BacklogRegistry();r.add(item("ITEM.1"));assert r.reconcile("ITEM.1").state is BacklogState.READY

def test_stale_closure_evidence_is_rejected():
 r=BacklogRegistry();r.add(item("ITEM.1"));ready=r.reconcile("ITEM.1");p=proof(ready)
 r._items["ITEM.1"]=replace(ready,title="Changed after validation")
 with pytest.raises(BacklogError,match="stale or bound"):r.close("ITEM.1",p)

def test_cross_item_closure_evidence_is_rejected():
 r=BacklogRegistry();r.add(item("ITEM.1"));r.add(item("ITEM.2"))
 a=r.reconcile("ITEM.1");r.reconcile("ITEM.2")
 with pytest.raises(BacklogError,match="stale or bound"):r.close("ITEM.2",proof(a))

def test_closure_evidence_requires_canonical_timestamp_and_digests():
 x=item("ITEM.1")
 with pytest.raises(BacklogError,match="timezone-aware"):ClosureEvidence("EVID.1",x.item_id,x.digest,datetime(2026,10,5),hashlib.sha256(b"x").hexdigest())
 with pytest.raises(BacklogError,match="sha256"):ClosureEvidence("EVID.1",x.item_id,"bad",datetime(2026,10,5,tzinfo=timezone.utc),hashlib.sha256(b"x").hexdigest())

def test_lifecycle_inputs_are_typed():
 with pytest.raises(BacklogError,match="SourceKind"):src(kind="gap")
 with pytest.raises(BacklogError,match="BacklogState"):item("ITEM.1",state="open")
