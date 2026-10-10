import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot,snapshot_digest
from skeleton.ai.model_runtime.training_admission import RuntimePromotionError,admit_candidate_model
from skeleton.ai.training.flgb_training_runtime import CandidateWeights,PromotionEvidence
from skeleton.ai.training.temporal_admission import TemporalTrainingAdmission

class TestTemporalNativeAdmission(unittest.TestCase):
 def setup_case(self):
  rt=NativeLLMRuntime(TinyTransformer(["a","b"],dim=4,ctx=4,seed=1)); cp=rt.checkpoint(); prior=rt.model_digest
  clone=TinyTransformer.from_snapshot(dict(cp["model"])); clone.E[0][0]+=0.125
  target=snapshot_digest(portable_model_snapshot(clone))
  c=CandidateWeights("candidate",target,"1"*64,prior)
  p=PromotionEvidence(c.digest,"2"*64,"3"*64,"4"*64,"5"*64,cp["digest"],"mirror",True,True,True,True)
  t=TemporalTrainingAdmission("ta","6"*64,"7"*64,"8"*64,"9"*64,p.exact_head_commit,prior,c.training_lineage_digest,"temporal-custodian",1)
  return rt,c,p,t,lambda m:setattr(m.E[0],"__dummy__",0) if False else m.E[0].__setitem__(0,m.E[0][0]+0.125)

 def test_temporal_admission_reaches_physical_runtime(self):
  rt,c,p,t,apply=self.setup_case()
  admitted,_,_=admit_candidate_model(rt,c,p,apply,admission_authority="runtime",temporal_admission=t)
  self.assertEqual(admitted.model_digest,c.weights_digest)

 def test_wrong_temporal_base_fails_before_mutation(self):
  rt,c,p,t,apply=self.setup_case(); prior=rt.model_digest
  bad=TemporalTrainingAdmission(t.admission_id,t.content_digest,t.learning_decision_digest,t.certificate_digest,t.certificate_registration_digest,t.exact_head_commit,"f"*64,t.dataset_digest,t.authority_id,t.epoch)
  with self.assertRaisesRegex(RuntimePromotionError,"temporal admission base model"):
   admit_candidate_model(rt,c,p,apply,admission_authority="runtime",temporal_admission=bad)
  self.assertEqual(rt.model_digest,prior); self.assertEqual(rt._current_model_digest(),prior)

 def test_wrong_temporal_head_fails_before_mutation(self):
  rt,c,p,t,apply=self.setup_case(); prior=rt.model_digest
  bad=TemporalTrainingAdmission(t.admission_id,t.content_digest,t.learning_decision_digest,t.certificate_digest,t.certificate_registration_digest,"f"*64,t.base_model_digest,t.dataset_digest,t.authority_id,t.epoch)
  with self.assertRaisesRegex(RuntimePromotionError,"exact-head"):
   admit_candidate_model(rt,c,p,apply,admission_authority="runtime",temporal_admission=bad)
  self.assertEqual(rt.model_digest,prior)

 def test_wrong_training_lineage_fails_before_mutation(self):
  rt,c,p,t,apply=self.setup_case(); prior=rt.model_digest
  bad=TemporalTrainingAdmission(t.admission_id,t.content_digest,t.learning_decision_digest,t.certificate_digest,t.certificate_registration_digest,t.exact_head_commit,t.base_model_digest,"e"*64,t.authority_id,t.epoch)
  with self.assertRaisesRegex(RuntimePromotionError,"training lineage"):
   admit_candidate_model(rt,c,p,apply,admission_authority="runtime",temporal_admission=bad)
  self.assertEqual(rt.model_digest,prior)

if __name__=="__main__": unittest.main()
