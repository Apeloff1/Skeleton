import pytest
from skeleton.simulation.scheduling import *
def test_simulation_is_non_authoritative_and_labels_assumptions():
 r=simulate(WorkloadTrace((1,2),("perfect parallelism",)),"fifo",2);assert not r.authoritative and r.trace.assumptions
def test_metrics_compare_policy_inputs_without_granting_authority():
 t=WorkloadTrace((1,2,3),("fixed durations",));a=simulate(t,"fifo",1);b=simulate(t,"edf",2)
 assert b.metric.throughput>a.metric.throughput and 0<=a.metric.fairness<=1
def test_unlabeled_or_invalid_trace_fails_closed():
 with pytest.raises(ValueError):WorkloadTrace((1,),())
 with pytest.raises(ValueError):WorkloadTrace((-1,),("x",))
def test_authoritative_simulation_cannot_be_forged():
 t=WorkloadTrace((1,),("x",))
 with pytest.raises(ValueError):SchedulingSimulation("x",t,SimulationMetric(1,1,1,1),True)

def test_nonfinite_duration_rejected():
 import pytest,math
 with pytest.raises(ValueError):WorkloadTrace((math.nan,),("trace",))
def test_bool_worker_count_rejected():
 import pytest
 with pytest.raises(ValueError):simulate(WorkloadTrace((1,),("trace",)),"fifo",True)

def test_nonfinite_metric_rejected():
 import pytest,math
 with pytest.raises(ValueError):SimulationMetric(math.nan,1,1,1)
