from skeleton.persistence.decision_graph import DecisionEdge,DecisionOutcome,DecisionRecord,DecisionRecordGraph
import pytest
D="a"*64
def rec(i,**kw): return DecisionRecord(i,D,**kw)
def test_append_preserves_history_and_links_impacts():
 g=DecisionRecordGraph((rec("d1",outcomes=(DecisionOutcome(DecisionEdge.ARTIFACT,"a1","created"),)),))
 g2=g.append(rec("d2",supersedes="d1",correction_reason="new evidence"))
 assert len(g.records)==1 and len(g2.records)==2
 assert g2.impact("d1")[0].target_id=="a1"
def test_supersession_requires_reason_and_existing_target():
 with pytest.raises(ValueError): rec("d2",supersedes="d1")
 with pytest.raises(ValueError): DecisionRecordGraph((rec("d2",supersedes="missing",correction_reason="fix"),))
def test_duplicate_or_cycle_fails_closed():
 with pytest.raises(ValueError): DecisionRecordGraph((rec("d1"),rec("d1")))
 a=rec("a",supersedes="b",correction_reason="x"); b=rec("b",supersedes="a",correction_reason="y")
 with pytest.raises(ValueError): DecisionRecordGraph((a,b))
def test_record_identity_is_deterministic():
 r=rec("d1"); assert r.record_digest==rec("d1").record_digest
