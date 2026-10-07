import unittest
from dataclasses import replace
from skeleton.ai.training.flgb_training_runtime import CandidateWeights,MirrorEvaluation,PromotionEvidence,digest_json
from skeleton.ai.training.project_learning import ProjectOutcome,LearningApproval,admit_project_outcome
from skeleton.ai.training.project_learning_run import build_project_learning_manifest
from skeleton.ai.training.lifecycle_proof import LifecycleProofError,prove_project_learning
from skeleton.ai.training.promotion_lifecycle import RuntimeAdmission,RollbackProof,extend_with_promotion
D="a"*64
def base():
 o=ProjectOutcome("o","t","p",D,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"successful")
 a=LearningApproval(o.digest,"learning-reviewer","1"*64,"2"*64,"3"*64,"project-learning",True)
 ad=admit_project_outcome(o,a,dataset_id="ds",source_id="project:o")
 r=build_project_learning_manifest(ad,run_id="run",base_model_digest=D,code_digest="b"*64,config_digest="c"*64,seed_manifest_digest="d"*64,max_steps=5,scope="project-learning")
 return prove_project_learning("cycle",o,a,ad,r)
def production():
 p=base(); c=CandidateWeights("candidate","4"*64,"5"*64,D)
 e=MirrorEvaluation("eval",c.digest,"6"*64,900000,800000,True,"mirror-verifier","7"*64)
 pe=PromotionEvidence(c.digest,"8"*64,"9"*64,"a"*64,digest_json(e.__dict__),"b"*64,"mirror-verifier",True,True,True,True)
 ra=RuntimeAdmission(c.digest,D,c.weights_digest,pe.rollback_digest,"runtime-custodian",True)
 rb=RollbackProof(ra.digest,ra.checkpoint_digest,D,"rollback-verifier",True)
 return p,c,e,pe,ra,rb
class TestPromotionLifecycle(unittest.TestCase):
 def test_full_cycle_is_contiguous_and_rollback_proven(self):
  x=extend_with_promotion(*production())
  self.assertEqual(x.stages[-1].stage,"rollback-ready")
  self.assertEqual(x.stages[-1].subject_digest,D)
  self.assertEqual(len(x.stages),9)
 def test_losing_candidate_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,replace(e,candidate_score_ppm=1),pe,ra,rb)
 def test_candidate_substitution_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,replace(c,weights_digest="0"*64),e,pe,ra,rb)
 def test_unqualified_promotion_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,e,replace(pe,rollback_ready=False),ra,rb)
 def test_non_atomic_runtime_swap_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): RuntimeAdmission(c.digest,D,c.weights_digest,pe.rollback_digest,"runtime",False)
 def test_wrong_runtime_weights_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,e,pe,replace(ra,admitted_model_digest="0"*64),rb)
 def test_false_rollback_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,e,pe,ra,replace(rb,verified=False))
 def test_rollback_to_wrong_model_rejected(self):
  p,c,e,pe,ra,rb=production()
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,e,pe,ra,replace(rb,restored_model_digest="0"*64))
 def test_evaluator_cannot_also_admit_runtime(self):
  p,c,e,pe,ra,rb=production(); ra=replace(ra,admission_authority=e.independent_verifier); rb=replace(rb,admission_digest=ra.digest)
  with self.assertRaises(LifecycleProofError): extend_with_promotion(p,c,e,pe,ra,rb)
if __name__=="__main__": unittest.main()
