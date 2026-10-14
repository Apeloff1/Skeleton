import pytest
from dataclasses import replace
from skeleton.ai.execution_recovery import RecoveryCheckpoint,ExecutionJournal,ConsumptionRecord

def cp(**kw):
 d=dict(workload_id="w1",authorization_id="auth:1",epoch=1,sequence=1,state_digest="state:a",previous_record_id=None);d.update(kw);return RecoveryCheckpoint(**d)

def test_consume_is_idempotent_for_same_authorization():
 j=ExecutionJournal();a=j.consume(cp());b=j.consume(cp());assert a==b;assert len(j.records())==1

def test_recovery_reconstructs_exact_state_and_identity():
 j=ExecutionJournal();r=j.consume(cp());k=j.recover(j.records());assert k.records()==(r,);assert k.head("w1")==r;assert k.consumed("auth:1")

def test_second_authorization_requires_chain_head():
 j=ExecutionJournal();r=j.consume(cp())
 with pytest.raises(PermissionError): j.consume(cp(authorization_id="auth:2",sequence=2))
 r2=j.consume(cp(authorization_id="auth:2",sequence=2,previous_record_id=r.record_id));assert r2.previous_record_id==r.record_id

def test_stale_epoch_and_sequence_fail_closed():
 j=ExecutionJournal();r=j.consume(cp(epoch=3,sequence=7))
 with pytest.raises(PermissionError): j.consume(cp(authorization_id="auth:2",epoch=2,sequence=8,previous_record_id=r.record_id))
 with pytest.raises(PermissionError): j.consume(cp(authorization_id="auth:3",epoch=3,sequence=7,previous_record_id=r.record_id))

def test_tampered_record_rejected_during_recovery():
 j=ExecutionJournal();r=j.consume(cp())
 with pytest.raises(ValueError): ExecutionJournal((replace(r,outcome="aborted"),))

def test_duplicate_authorization_in_import_is_rejected():
 j=ExecutionJournal();r=j.consume(cp())
 forged=ConsumptionRecord(r.record_id,r.authorization_id,r.workload_id,r.epoch,r.sequence,r.checkpoint_id,r.previous_record_id,r.outcome)
 with pytest.raises(ValueError): ExecutionJournal((r,forged))

def test_cross_workload_chain_substitution_rejected():
 j=ExecutionJournal();r=j.consume(cp())
 with pytest.raises(PermissionError): j.consume(cp(workload_id="w2",authorization_id="auth:2",sequence=2,previous_record_id=r.record_id))

def test_abort_is_terminal_and_idempotent():
 j=ExecutionJournal();r=j.consume(cp(),outcome="aborted");assert r.outcome=="aborted";assert j.consume(cp(),outcome="committed")==r

def test_checkpoint_identity_binds_recovery_state():
 assert cp().checkpoint_id!=cp(state_digest="state:b").checkpoint_id
