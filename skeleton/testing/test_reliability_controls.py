import pytest
from skeleton.ai.runtime.deferred.reliability_controls import *
def test_backpressure_bounds_buffer_and_throttles_before_saturation():
 l=BufferLimit(10,8); assert pressure(BackpressureSignal(8,l)).throttle
 assert not pressure(BackpressureSignal(10,l)).accept_new
def test_cancellation_is_explicit_under_pressure():
 d=pressure(BackpressureSignal(1,BufferLimit(10,8),True)); assert d.cancelled and not d.accept_new
def test_load_shedding_never_drops_security_audit_or_authority():
 p=LoadShedPolicy(tuple(WorkClass))
 for k in (WorkClass.SECURITY,WorkClass.AUDIT,WorkClass.AUTHORITY): assert not shed(p,k).shed
def test_optional_work_has_explicit_degraded_response_when_shed():
 d=shed(LoadShedPolicy((WorkClass.OPTIONAL,)),WorkClass.OPTIONAL); assert d.shed and d.degraded_response
def test_congestion_differentiates_new_retry_and_recovery():
 b=QueueBudget(10,100); s=CongestionState(10,1,1)
 assert not queue_decision(b,s,QueueKind.NEW).admit
 assert not queue_decision(b,s,QueueKind.RETRY).admit
 assert queue_decision(b,s,QueueKind.RECOVERY).admit
def test_retry_only_transient_idempotent_and_shared_budget_identity():
 b=RetryBudget("x",2)
 assert not retry(b,RetryAttempt("x",FailureClass.PERMANENT,True)).allowed
 assert not retry(b,RetryAttempt("x",FailureClass.TRANSIENT,False)).allowed
 assert not retry(b,RetryAttempt("other",FailureClass.TRANSIENT,True)).allowed
def test_nested_retry_consumes_same_budget_until_exhausted():
 b=RetryBudget("x",1); d=retry(b,RetryAttempt("x",FailureClass.TRANSIENT,True))
 assert d.allowed and not retry(d.next_budget,RetryAttempt("x",FailureClass.TRANSIENT,True)).allowed
def test_breaker_probe_is_dependency_scoped():
 b=CircuitBreaker("db","storage",BreakerState.OPEN,3,3)
 with pytest.raises(ValueError): breaker(b,ProbeResult("api",True))
def test_open_breaker_requires_probe_to_restore_primary():
 b=CircuitBreaker("db","storage",BreakerState.OPEN,3,3)
 assert not breaker(b).allow_primary
 assert breaker(b,ProbeResult("db",True)).allow_primary
def test_fallback_is_only_signaled_when_policy_compatible():
 b=CircuitBreaker("db","storage",BreakerState.OPEN,3,3)
 assert not breaker(b,fallback_policy_compatible=False).fallback_allowed
 assert breaker(b,fallback_policy_compatible=True).fallback_allowed
