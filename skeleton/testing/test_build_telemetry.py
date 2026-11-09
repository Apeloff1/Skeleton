from skeleton.automation.build_telemetry import BuildTelemetry
def test_rates():assert BuildTelemetry(2,3,1,1,0,2.0).acceptance_rate==.75
