from __future__ import annotations
import hashlib
from skeleton.training.observability import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def trace(t=10):return TrainingTrace("RUN.1",S("state"),t)
def test_non_finite_value_alerts_without_serializing_sample_data():assert TrainingMonitor().evaluate(TrainingMetric("RUN.1","METRIC.LOSS",float("nan"),11),trace(),11,5,1,100)[0].kind is AlertKind.NON_FINITE
def test_stall_alert():assert AlertKind.STALL in {a.kind for a in TrainingMonitor().evaluate(TrainingMetric("RUN.1","METRIC.LOSS",1,20),trace(10),20,5,1,100)}
def test_throughput_collapse_alert():assert AlertKind.THROUGHPUT in {a.kind for a in TrainingMonitor().evaluate(TrainingMetric("RUN.1","METRIC.THROUGHPUT",.2,11),trace(),11,5,1,100)}
def test_resource_anomaly_alert():assert AlertKind.RESOURCE in {a.kind for a in TrainingMonitor().evaluate(TrainingMetric("RUN.1","METRIC.RESOURCE",101,11),trace(),11,5,1,100)}
def test_trace_requires_digest_not_raw_payload():
 try:TrainingTrace("RUN.1","raw training sample",1)
 except ObservabilityError:return
 assert False
