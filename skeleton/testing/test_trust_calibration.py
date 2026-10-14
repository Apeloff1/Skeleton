from skeleton.eval.trust_calibration import *
def test_degraded_mode_is_never_hidden_by_high_confidence():
 p=present_trust(TrustSignal(.99,.01,True,("e",)));assert p.label=="degraded" and p.degraded
def test_uncertainty_is_presented_separately_from_confidence():
 p=present_trust(TrustSignal(.9,.8,False,("e",)));assert p.label=="uncertain" and p.confidence==.9 and p.uncertainty==.8
def test_predicted_confidence_compares_to_observed_outcome():
 e=calibration_error((CalibrationObservation(.9,True),CalibrationObservation(.8,False)));assert abs(e-.45)<1e-9

def test_empty_evidence_is_never_evidence_backed():assert present_trust(TrustSignal(.9,.1,False,())).label=="uncertain"
def test_nonfinite_confidence_rejected():
 import pytest,math
 with pytest.raises(ValueError):TrustSignal(math.nan,.1,False,("e",))

def test_duplicate_or_empty_evidence_rejected():
 import pytest
 with pytest.raises(ValueError):TrustSignal(.5,.1,False,("e","e"))
 with pytest.raises(ValueError):TrustSignal(.5,.1,False,("",))
