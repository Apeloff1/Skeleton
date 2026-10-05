import pytest
from skeleton.ai.saga_workflows import *
def d():return SagaDefinition("s",("a","b"),("ka","kb"),30)
def test_transition_is_durable_and_idempotent():
 i=SagaInstance(d());t=advance(i,"a");assert t.durable and advance(t.after,"a").after==t.after
def test_out_of_order_step_rejected():
 with pytest.raises(ValueError):advance(SagaInstance(d()),"b")
