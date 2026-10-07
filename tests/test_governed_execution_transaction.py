import pytest
from skeleton.ai.governed_execution_transaction import AdmissionBinding,PlacementBinding,CheckpointBinding,bind_transaction,terminal_receipt,validate_terminal

def a(**kw):
 d=dict(authorization_id="auth:1",plan_id="plan:1",resource_lease_id="lease:1",lease_generation=3,expires_at_ns=200);d.update(kw);return AdmissionBinding(**d)
def p(**kw):
 d=dict(receipt_id="place:1",snapshot_id="topo:1",topology_generation=4,workload_id="w1",resource_lease_id="lease:1",operation_id="op:1");d.update(kw);return PlacementBinding(**d)
def c(**kw):
 d=dict(checkpoint_id="cp:1",workload_id="w1",authorization_id="auth:1",epoch=2,sequence=7,previous_record_id=None);d.update(kw);return CheckpointBinding(**d)

def test_transaction_identity_is_deterministic():
 assert bind_transaction(a(),p(),c(),150)==bind_transaction(a(),p(),c(),150)

def test_expired_admission_fails_closed():
 with pytest.raises(PermissionError): bind_transaction(a(),p(),c(),200)

def test_cross_lease_placement_rejected():
 with pytest.raises(PermissionError): bind_transaction(a(),p(resource_lease_id="lease:2"),c(),150)

def test_cross_authorization_checkpoint_rejected():
 with pytest.raises(PermissionError): bind_transaction(a(),p(),c(authorization_id="auth:2"),150)

def test_cross_workload_checkpoint_rejected():
 with pytest.raises(PermissionError): bind_transaction(a(),p(),c(workload_id="w2"),150)

@pytest.mark.parametrize("mutation",[{"receipt_id":"place:2"},{"snapshot_id":"topo:2"},{"topology_generation":5},{"operation_id":"op:2"}])
def test_placement_identity_changes_transaction(mutation):
 assert bind_transaction(a(),p(**mutation),c(),150).transaction_id!=bind_transaction(a(),p(),c(),150).transaction_id

def test_recovery_epoch_and_sequence_bind_transaction():
 assert bind_transaction(a(),p(),c(epoch=3),150).transaction_id!=bind_transaction(a(),p(),c(),150).transaction_id
 assert bind_transaction(a(),p(),c(sequence=8),150).transaction_id!=bind_transaction(a(),p(),c(),150).transaction_id

def test_terminal_receipt_is_evidence_order_canonical():
 t=bind_transaction(a(),p(),c(),150);assert terminal_receipt(t,"consume:1","committed",("e:b","e:a"))==terminal_receipt(t,"consume:1","committed",("e:a","e:b"))

def test_terminal_receipt_requires_evidence_and_rejects_duplicates():
 t=bind_transaction(a(),p(),c(),150)
 with pytest.raises(ValueError): terminal_receipt(t,"consume:1","committed",())
 with pytest.raises(ValueError): terminal_receipt(t,"consume:1","committed",("e:a","e:a"))

def test_terminal_substitution_rejected():
 t=bind_transaction(a(),p(),c(),150);r=terminal_receipt(t,"consume:1","committed",("e:a",))
 with pytest.raises(PermissionError): validate_terminal(r,t,"consume:2","committed",("e:a",))
 with pytest.raises(PermissionError): validate_terminal(r,t,"consume:1","aborted",("e:a",))
