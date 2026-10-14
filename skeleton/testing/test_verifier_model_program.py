from __future__ import annotations
import hashlib,pytest
from skeleton.training.verifier_models import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def models(): return (VerifierModel("VERIFY.A",S("a"),"FAMILY.A"),VerifierModel("VERIFY.B",S("b"),"FAMILY.B"))
def c(i,fa=.01): return VerifierCalibration(i,fa,.02,1000)
def test_verifier_confidence_is_separate_from_generator_identity(): assert VerificationScore("VERIFY.A","GENERATOR.A",.8,True).accepted
def test_generator_cannot_self_verify():
 with pytest.raises(VerifierError,match="independent"): VerificationScore("MODEL.A","MODEL.A",.9,True)
def test_diverse_calibrated_ensemble_is_eligible(): assert ensemble_eligible(models(),(c("VERIFY.A"),c("VERIFY.B")),.05)
def test_rubber_stamp_false_accept_rate_blocks_ensemble(): assert not ensemble_eligible(models(),(c("VERIFY.A",.2),c("VERIFY.B")),.05)
def test_shared_training_family_is_not_diverse():
 ms=(VerifierModel("VERIFY.A",S("a"),"FAMILY.SAME"),VerifierModel("VERIFY.B",S("b"),"FAMILY.SAME")); assert not ensemble_eligible(ms,(c("VERIFY.A"),c("VERIFY.B")),.05)