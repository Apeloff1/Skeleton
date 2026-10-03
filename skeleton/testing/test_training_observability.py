from skeleton.learning.training_observability import *
def test_nonfinite_stall_and_throughput_collapse_alert_without_raw_data():
 t=TrainingTelemetry(minimum_throughput=10); assert t.record(TrainingMetric("r",1,"loss",float("nan")))[0].code=="non_finite_value"; assert t.record(TrainingMetric("r",2,"throughput",2.0))[0].code=="throughput_collapse"; assert t.stall(run_id="r",last_step=2,current_step=2).code=="training_stall"
