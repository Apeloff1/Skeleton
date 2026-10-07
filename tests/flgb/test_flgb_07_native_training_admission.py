import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot,snapshot_digest
from skeleton.ai.model_runtime.training_admission import RuntimePromotionError,AdmissionLedger,admit_candidate_model,execute_rollback
from skeleton.ai.training.flgb_training_runtime import CandidateWeights,PromotionEvidence

def setup():
 rt=NativeLLMRuntime(TinyTransformer(["a","b"],dim=4,ctx=4,seed=1))
 cp=rt.checkpoint(); prior=rt.model_digest
 clone=TinyTransformer.from_snapshot(dict(cp["model"]))
 clone.E[0][0]+=0.125
 target=snapshot_digest(portable_model_snapshot(clone))
 c=CandidateWeights("candidate",target,"1"*64,prior)
 p=PromotionEvidence(c.digest,"2"*64,"3"*64,"4"*64,"5"*64,cp["digest"],"mirror-verifier",True,True,True,True)
 def apply(m): m.E[0][0]+=0.125
 return rt,cp,prior,c,p,apply

class TestNativeTrainingAdmission(unittest.TestCase):
 def test_observed_state_changes_and_rollback_is_proven(self):
  rt,cp,prior,c,p,apply=setup()
  admitted,a,rb=admit_candidate_model(rt,c,p,apply,admission_authority="runtime-custodian")
  self.assertEqual(admitted.model_digest,c.weights_digest)
  self.assertNotEqual(admitted.model_digest,prior)
  self.assertEqual(a.prior_model_digest,prior)
  self.assertEqual(rb.restored_model_digest,prior)
  self.assertEqual(NativeLLMRuntime.restore(cp).model_digest,prior)
  executed=execute_rollback(admitted,a,rb,cp)
  self.assertTrue(executed.executed)
  self.assertEqual(admitted.model_digest,prior)
  self.assertEqual(admitted._current_model_digest(),prior)
 def test_rollback_refuses_runtime_drift_after_admission(self):
  rt,cp,prior,c,p,apply=setup()
  admitted,a,rb=admit_candidate_model(rt,c,p,apply,admission_authority="runtime")
  admitted.model.E[0][0]+=1
  with self.assertRaises(RuntimePromotionError): execute_rollback(admitted,a,rb,cp)
 def test_promotion_receipt_is_single_use_when_ledger_enabled(self):
  rt,cp,prior,c,p,apply=setup(); ledger=AdmissionLedger()
  admit_candidate_model(rt,c,p,apply,admission_authority="runtime",ledger=ledger)
  fresh=NativeLLMRuntime.restore(cp)
  with self.assertRaisesRegex(RuntimePromotionError,"already consumed"):
   admit_candidate_model(fresh,c,p,apply,admission_authority="runtime",ledger=ledger)
 def test_ledger_snapshot_survives_restart_and_rejects_replay(self):
  rt,cp,prior,c,p,apply=setup(); ledger=AdmissionLedger()
  admit_candidate_model(rt,c,p,apply,admission_authority="runtime",ledger=ledger)
  recovered=AdmissionLedger.restore(ledger.snapshot()); fresh=NativeLLMRuntime.restore(cp)
  with self.assertRaisesRegex(RuntimePromotionError,"already consumed"):
   admit_candidate_model(fresh,c,p,apply,admission_authority="runtime",ledger=recovered)
 def test_tampered_ledger_snapshot_is_rejected(self):
  ledger=AdmissionLedger(); snap=ledger.snapshot(); snap["promotions"]=["f"*64]
  with self.assertRaisesRegex(RuntimePromotionError,"invalid admission ledger snapshot"): AdmissionLedger.restore(snap)
 def test_ledger_rejects_duplicate_and_invalid_receipts(self):
  with self.assertRaises(RuntimePromotionError): AdmissionLedger(("a"*64,"a"*64),())
  with self.assertRaises(Exception): AdmissionLedger(("not-a-digest",),())
 def test_admission_authority_must_be_independent(self):
  rt,cp,prior,c,p,apply=setup()
  with self.assertRaisesRegex(RuntimePromotionError,"authorities must be separate"):
   admit_candidate_model(rt,c,p,apply,admission_authority=p.independent_verifier)
 def test_admitter_cannot_certify_own_live_rollback(self):\n  rt,cp,prior,c,p,apply=setup()\n  admitted,a,rb=admit_candidate_model(rt,c,p,apply,admission_authority="runtime")\n  with self.assertRaisesRegex(RuntimePromotionError,"must differ"):\n   execute_rollback(admitted,a,rb,cp,verifier_id="runtime")\n def test_rollback_rejects_different_valid_checkpoint(self):
  rt,cp,prior,c,p,apply=setup()
  admitted,a,rb=admit_candidate_model(rt,c,p,apply,admission_authority="runtime")
  other=NativeLLMRuntime(TinyTransformer(["a","b"],dim=4,ctx=4,seed=2)).checkpoint()
  with self.assertRaisesRegex(RuntimePromotionError,"checkpoint identity mismatch"):
   execute_rollback(admitted,a,rb,other)
 def test_declared_digest_cannot_lie_about_observed_weights(self):
  rt,cp,prior,c,p,apply=setup()
  c=CandidateWeights("candidate","f"*64,c.training_lineage_digest,prior)
  p=PromotionEvidence(c.digest,p.exact_head_commit,p.rights_digest,p.contamination_scan_digest,p.evaluation_digest,p.rollback_digest,p.independent_verifier,True,True,True,True)
  with self.assertRaises(RuntimePromotionError): admit_candidate_model(rt,c,p,apply,admission_authority="runtime")
 def test_failed_apply_restores_from_checkpoint_before_propagating(self):
  rt,cp,prior,c,p,apply=setup()
  def bad(m): m.E[0][0]+=9; raise RuntimeError("training loader failed")
  with self.assertRaises(RuntimeError): admit_candidate_model(rt,c,p,bad,admission_authority="runtime")
  self.assertEqual(rt.model_digest,prior)
  self.assertEqual(rt._current_model_digest(),prior)
  self.assertEqual(NativeLLMRuntime.restore(cp).model_digest,prior)
 def test_unqualified_promotion_cannot_touch_model(self):
  rt,cp,prior,c,p,apply=setup()
  p=PromotionEvidence(c.digest,p.exact_head_commit,p.rights_digest,p.contamination_scan_digest,p.evaluation_digest,p.rollback_digest,p.independent_verifier,True,True,False,True)
  with self.assertRaises(RuntimePromotionError): admit_candidate_model(rt,c,p,apply,admission_authority="runtime")
  self.assertEqual(rt.model_digest,prior)
if __name__=="__main__": unittest.main()
