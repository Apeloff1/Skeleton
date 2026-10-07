import pytest
from skeleton.ai.saga_workflows import *
def d():return SagaDefinition("s",("a","b"),("ka","kb"),30)
def test_transition_is_durable_and_idempotent():
 i=SagaInstance(d());t=advance(i,"a");assert t.durable and advance(t.after,"a").after==t.after
def test_out_of_order_step_rejected():
 with pytest.raises(ValueError):advance(SagaInstance(d()),"b")

def test_mismatched_idempotency_keys_rejected():
 with pytest.raises(ValueError):SagaDefinition("s",("a","b"),("ka",),30)
def test_timeout_enters_reconciliation_state():
 i=SagaInstance(d(),started_at=10);t=advance(i,"a",40);assert t.reconciliation_required and t.after.failed=="timeout"
