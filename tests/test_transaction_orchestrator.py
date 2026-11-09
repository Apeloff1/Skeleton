import pytest
from dataclasses import replace
from skeleton.ai.transaction_orchestrator import OrchestrationIntent,TransactionOrchestrator,recover

def intent(**kw):
 d=dict(transaction_id="txn:1",operation_id="op:1",deadline_ns=200,compensation_id="comp:1",evidence_ids=("e:auth","e:place"));d.update(kw);return OrchestrationIntent(**d)

def test_prepare_commit_chain_is_deterministic_and_linked():
 o=TransactionOrchestrator(intent());p=o.transition("prepared",100,"resources-ready");c=o.transition("committed",150,"execution-complete",("e:consume",));assert c.previous_receipt_id==p.receipt_id;assert o.phase=="committed"

def test_expired_transaction_cannot_prepare_or_commit():
 o=TransactionOrchestrator(intent())
 with pytest.raises(PermissionError):o.transition("prepared",200,"late")
 o=TransactionOrchestrator(intent());o.transition("prepared",100,"ready")
 with pytest.raises(PermissionError):o.transition("committed",200,"late")

def test_expired_transaction_can_abort():
 o=TransactionOrchestrator(intent());r=o.transition("aborted",250,"deadline");assert r.to_phase=="aborted"

def test_prepared_abort_requires_compensation_identity():
 o=TransactionOrchestrator(intent(compensation_id=None));o.transition("prepared",100,"ready")
 with pytest.raises(PermissionError):o.transition("aborted",110,"failure")

def test_abort_binds_compensation_evidence():
 o=TransactionOrchestrator(intent());o.transition("prepared",100,"ready");r=o.transition("aborted",110,"failure");assert "comp:1" in r.evidence_ids

def test_terminal_state_is_immutable():
 o=TransactionOrchestrator(intent());o.transition("aborted",100,"cancelled")
 with pytest.raises(PermissionError):o.transition("prepared",110,"retry")

def test_invalid_phase_skip_fails_closed():
 o=TransactionOrchestrator(intent())
 with pytest.raises(PermissionError):o.transition("committed",100,"skip")

def test_crash_recovery_reconstructs_phase_and_head():
 o=TransactionOrchestrator(intent());p=o.transition("prepared",100,"ready");r=recover(intent(),o.receipts());assert r.phase=="prepared";assert r.head_id==p.receipt_id;r.transition("committed",150,"done")

def test_tampered_history_rejected():
 o=TransactionOrchestrator(intent());p=o.transition("prepared",100,"ready")
 with pytest.raises(ValueError):recover(intent(),(replace(p,reason="forged"),))

def test_foreign_transaction_history_rejected():
 o=TransactionOrchestrator(intent());p=o.transition("prepared",100,"ready")
 with pytest.raises(ValueError):recover(intent(transaction_id="txn:2"),(p,))

def test_evidence_is_canonical_across_input_order():
 a=TransactionOrchestrator(intent(evidence_ids=("e:b","e:a"))).transition("prepared",100,"ready",("e:c",))
 b=TransactionOrchestrator(intent(evidence_ids=("e:a","e:b"))).transition("prepared",100,"ready",("e:c",))
 assert a==b
