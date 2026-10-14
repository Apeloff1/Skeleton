from dataclasses import replace
import pytest
from skeleton.ai.crossplane_bindings import *

class O:pass
def sched():
 r=O();r.epoch=1;r.task_id="step";r.worker_id="w";r.worker_generation=2;r.units=3;r.effective_priority=5;r.evidence_id="ev";r.reservation_id=scheduling_identity(1,"step","w",2,3,5,"ev");return r
class R:cpu=1;gpu=0;ram_bytes=2;tokens=3
def resources():
 r=O();r.scope_path=("tenant","wf");r.generation=7;r.resources=R();r.deadline_ns=100;r.evidence_id="rev";r.reservation_id=resource_identity(r.scope_path,7,r.resources,100,"rev");return r
def owner():
 r=O();r.workflow_id="wf";r.step_id="step";r.coordinator_epoch=4;r.worker_id="w";r.worker_generation=2;r.issued_at_ns=10;r.expires_at_ns=90;r.lease_id=ownership_identity("wf","step",4,"w",2,10,90);return r
def ctx():return AdmissionContext("txn","wf","step",7,100,"w",2)

def test_valid_artifacts_bind():
 assert bind_schedule(ctx(),sched()).participant=="schedule"
 assert bind_resources(ctx(),resources()).participant=="resources"
 assert bind_ownership(ctx(),owner()).participant=="ownership"

def test_forged_schedule_identity_rejected():
 r=sched();r.reservation_id="forged"
 with pytest.raises(PermissionError):bind_schedule(ctx(),r)

def test_schedule_worker_substitution_rejected_even_with_valid_identity():
 r=sched();r.worker_id="other";r.reservation_id=scheduling_identity(r.epoch,r.task_id,r.worker_id,r.worker_generation,r.units,r.effective_priority,r.evidence_id)
 with pytest.raises(PermissionError):bind_schedule(ctx(),r)

def test_forged_resource_identity_rejected():
 r=resources();r.deadline_ns=99
 with pytest.raises(PermissionError):bind_resources(ctx(),r)

def test_resource_generation_substitution_rejected_with_recomputed_id():
 r=resources();r.generation=8;r.reservation_id=resource_identity(r.scope_path,8,r.resources,r.deadline_ns,r.evidence_id)
 with pytest.raises(PermissionError):bind_resources(ctx(),r)

def test_forged_ownership_identity_rejected():
 r=owner();r.worker_generation=3
 with pytest.raises(PermissionError):bind_ownership(ctx(),r)

def test_ownership_cannot_outlive_transaction():
 r=owner();r.expires_at_ns=101;r.lease_id=ownership_identity(r.workflow_id,r.step_id,r.coordinator_epoch,r.worker_id,r.worker_generation,r.issued_at_ns,r.expires_at_ns)
 with pytest.raises(PermissionError):bind_ownership(ctx(),r)

def test_prepare_identity_binds_verified_artifact():
 b=bind_schedule(ctx(),sched());a=prepare_identity(ctx(),b)
 assert a==prepare_identity(ctx(),b)
 assert a!=prepare_identity(replace(ctx(),generation=8),b)
