from skeleton.automation.build_slo import evaluate
from skeleton.automation.build_telemetry import BuildTelemetry
def test_low_acceptance_detected():assert "acceptance_rate" in evaluate(BuildTelemetry(5,1,0,9,0,1)).violations
