import math,pytest
from skeleton.ai.build.change_risk import *
def test_failed_hard_gate_cannot_be_overridden_by_low_risk():assert not estimate_risk((RiskFactor("x",0,1),),hard_gates_passed=False).admissible
@pytest.mark.parametrize("x",[math.nan,math.inf,True])
def test_nonfinite_and_bool_risk_values_rejected(x):
 with pytest.raises(ValueError):estimate_risk((RiskFactor("x",x,1),),hard_gates_passed=True)
def test_calibration_validates_probability():
 with pytest.raises(ValueError):calibration_error((RiskCalibration(2,False),))
