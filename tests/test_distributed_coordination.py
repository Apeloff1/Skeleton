import pytest
from dataclasses import replace
from skeleton.ai.distributed_coordination import Participant,ParticipantManifest,acknowledge,decide,compensation_order

def m(**kw):
 ps=(Participant("p1",2,"storage","undo:storage"),Participant("p2",4,"compute","undo:compute"),Participant("p3",1,"evidence","undo:evidence"))
 d=dict(transaction_id="txn:1",participants=ps,policy="all",quorum=3,deadline_ns=200);d.update(kw);return ParticipantManifest(**d)
def ack(manifest,p,g,ok=True,e="e:1"): return acknowledge(manifest,p,g,ok,e,100)

def test_manifest_identity_is_order_independent():
 x=m();assert x.manifest_id==m(participants=tuple(reversed(x.participants))).manifest_id

def test_generation_fencing_rejects_stale_participant():
 with pytest.raises(PermissionError):ack(m(),"p1",1)

def test_foreign_participant_rejected():
 with pytest.raises(PermissionError):ack(m(),"p9",1)

def test_late_ack_is_classified_as_timeout():
 with pytest.raises(TimeoutError):acknowledge(m(),"p1",2,True,"e",200)

def test_all_policy_commits_only_when_all_prepare():
 x=m();acks=(ack(x,"p1",2),ack(x,"p2",4),ack(x,"p3",1));assert decide(x,acks,150).decision=="commit"
 assert decide(x,acks[:2],150).decision=="pending"

def test_all_policy_rejection_aborts_immediately():
 x=m();assert decide(x,(ack(x,"p1",2,False),),120).decision=="abort"

def test_timeout_aborts_insufficient_prepare():
 x=m();assert decide(x,(ack(x,"p1",2),),200).decision=="abort"

def test_quorum_policy_can_commit_with_missing_participant():
 x=m(policy="quorum",quorum=2);d=decide(x,(ack(x,"p1",2),ack(x,"p2",4)),120);assert d.decision=="commit";assert d.missing_ids==("p3",)

def test_duplicate_ack_rejected():
 x=m();a=ack(x,"p1",2)
 with pytest.raises(ValueError):decide(x,(a,a),120)

def test_foreign_or_tampered_ack_rejected():
 x=m();a=ack(x,"p1",2)
 with pytest.raises(PermissionError):decide(x,(replace(a,manifest_id="manifest:other"),),120)

def test_abort_compensates_prepared_participants_in_reverse_canonical_order():
 x=m();d=decide(x,(ack(x,"p1",2),ack(x,"p2",4),ack(x,"p3",1,False)),120);assert d.decision=="abort";assert compensation_order(x,d)==("undo:compute","undo:storage")

def test_compensation_cannot_run_for_commit():
 x=m();d=decide(x,(ack(x,"p1",2),ack(x,"p2",4),ack(x,"p3",1)),120)
 with pytest.raises(PermissionError):compensation_order(x,d)
