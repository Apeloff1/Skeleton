from dataclasses import replace
import pytest
from skeleton.ai.governed_execution_authority import *

def a():
 return ExecutionAuthority.issue("txn","wf","step",3,"worker",4,"sched","resource","lease",10,100,("ev:a","ev:b","ev:c"))

def args():
 return (20,"txn","wf","step",3,"worker",4,"sched","resource","lease")

def test_authority_is_deterministic_and_live():
 assert a()==a() and validate(a(),*args())

def test_evidence_order_is_canonical():
 x=ExecutionAuthority.issue("txn","wf","step",3,"worker",4,"sched","resource","lease",10,100,("ev:c","ev:a","ev:b"))
 assert x==a()

def test_tampered_authority_identity_rejected():
 x=replace(a(),worker_generation=5)
 with pytest.raises(PermissionError):validate(x,*args())

def test_validly_reissued_worker_substitution_rejected_by_context():
 x=ExecutionAuthority.issue("txn","wf","step",3,"other",4,"sched","resource","lease",10,100,("ev:a","ev:b","ev:c"))
 with pytest.raises(PermissionError):validate(x,*args())

def test_expired_and_preissue_authority_rejected():
 with pytest.raises(PermissionError):validate(a(),100,*args()[1:])
 with pytest.raises(PermissionError):validate(a(),9,*args()[1:])

def test_specialized_authority_is_subordinate():
 s=SpecializedAuthority.bind(a(),"speculative","spec-auth","ev:spec")
 assert s.execution_authority_id==a().authority_id and s.subordinate_authority_id=="spec-auth"

def test_single_use_ledger_exact_retry_is_idempotent():
 l=AuthorityLedger();x=l.consume(a(),"op","committed","ev");assert l.consume(a(),"op","committed","ev")==x

def test_single_use_ledger_rejects_conflicting_retry():
 l=AuthorityLedger();l.consume(a(),"op","committed","ev")
 with pytest.raises(PermissionError):l.consume(a(),"other","committed","ev")

def test_recovery_rejects_forged_consumption():
 good=AuthorityLedger().consume(a(),"op","committed","ev")
 bad=replace(good,outcome="aborted")
 with pytest.raises(PermissionError):AuthorityLedger((bad,))
