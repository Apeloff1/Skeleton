import pytest
from skeleton.agents.swarm_batch import preflight,submit_batch
from skeleton.agents.swarm_circuit import CircuitBreaker,CircuitState
from skeleton.agents.swarm_observability import event_counts,metrics,prometheus
from skeleton.agents.swarm_quota import Quota,QuotaExceeded,QuotaLedger
from skeleton.agents.swarm_runtime import AdmissionError,SwarmRuntime,SwarmTask

def test_quota_is_fail_closed_without_partial_accounting():
 q=QuotaLedger(Quota(max_queued=2)); q.reserve("tenant",queued=2)
 with pytest.raises(QuotaExceeded): q.reserve("tenant",queued=1)
 assert q.usage("tenant").queued==2

def test_quota_release_reclaims_capacity():
 q=QuotaLedger(Quota(max_queued=2)); q.reserve("x",queued=2); q.release("x",queued=1); assert q.usage("x").queued==1

def test_circuit_opens_and_half_opens_after_timeout():
 now=[0.0]; c=CircuitBreaker(failure_threshold=2,recovery_seconds=5,clock=lambda:now[0]); c.failure("w"); c.failure("w")
 assert c.allow("w") is False and c.circuit("w").state is CircuitState.OPEN
 now[0]=5; assert c.allow("w") is True and c.circuit("w").state is CircuitState.HALF_OPEN

def test_half_open_success_closes_circuit():
 c=CircuitBreaker(failure_threshold=1); c.failure("w"); c.success("w"); assert c.circuit("w").state is CircuitState.CLOSED

def test_batch_preflight_rejects_internal_duplicates_atomically():
 r=SwarmRuntime()
 with pytest.raises(AdmissionError): submit_batch(r,[SwarmTask("x",{}),SwarmTask("x",{})])
 assert r.tasks()==()

def test_batch_preflight_rejects_existing_id_atomically():
 r=SwarmRuntime(); r.submit(SwarmTask("existing",{}))
 with pytest.raises(AdmissionError): preflight(r,[SwarmTask("new",{}),SwarmTask("existing",{})])
 assert r.task("new") is None

def test_batch_submission_preserves_order():
 r=SwarmRuntime(); result=submit_batch(r,[SwarmTask("a",{}),SwarmTask("b",{})]); assert result.task_ids==("a","b")

def test_metrics_project_runtime_without_high_cardinality_labels():
 r=SwarmRuntime(); r.submit(SwarmTask("a",{})); m=metrics(r); assert m["queued"]==1 and m["queue_per_worker"]==1
 text=prometheus(r); assert "skeleton_swarm_queued 1" in text

def test_event_counts_aggregate_lifecycle():
 r=SwarmRuntime(); r.submit(SwarmTask("a",{})); assert event_counts(r)["task.submitted"]==1
