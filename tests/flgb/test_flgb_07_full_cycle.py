"""End-to-end governed learning to physical runtime integration."""
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_checkpoint import portable_model_snapshot,snapshot_digest
from skeleton.ai.model_runtime.training_admission import admit_candidate_model,execute_rollback
from skeleton.ai.training.flgb_training_runtime import CandidateWeights,MirrorEvaluation,PromotionEvidence,digest_json
from skeleton.ai.training.project_learning import ProjectOutcome,LearningApproval,admit_project_outcome
from skeleton.ai.training.project_learning_run import build_project_learning_manifest
from skeleton.ai.training.lifecycle_proof import prove_project_learning
from skeleton.ai.training.promotion_lifecycle import extend_with_promotion

class TestFullCycle(unittest.TestCase):
 def test_full_cycle(self):
  rt=NativeLLMRuntime(TinyTransformer(["a","b"],dim=4,ctx=4,seed=7)); old=rt.model_digest; cp=rt.checkpoint()
  o=ProjectOutcome("out","tenant","project","1"*64,rt.model_identity.identity_digest,"2"*64,"3"*64,"4"*64,"5"*64,"successful")
  a=LearningApproval(o.digest,"learning-reviewer","6"*64,"7"*64,"8"*64,"project-learning",True)
  ad=admit_project_outcome(o,a,dataset_id="dataset",source_id="project-out")
  run=build_project_learning_manifest(ad,run_id="train",base_model_digest=old,code_digest="9"*64,config_digest="a"*64,seed_manifest_digest="b"*64,max_steps=10,scope="project-learning")
  proof=prove_project_learning("cycle",o,a,ad,run)
  model=TinyTransformer.from_snapshot(dict(cp["model"])); model.E[0][0]+=0.25
  cand=CandidateWeights("candidate",snapshot_digest(portable_model_snapshot(model)),run.manifest.digest,old)
  ev=MirrorEvaluation("mirror",cand.digest,old,900000,800000,True,"mirror-verifier","c"*64)
  prom=PromotionEvidence(cand.digest,"d"*64,ad.rights.digest,a.contamination_scan_digest,digest_json(ev.__dict__),cp["digest"],"mirror-verifier",True,True,True,True)
  def apply(m): m.E[0][0]+=0.25
  rt,adm,rb=admit_candidate_model(rt,cand,prom,apply,admission_authority="runtime-custodian")
  ready=extend_with_promotion(proof,cand,ev,prom,adm,rb)
  self.assertEqual(rt.model_digest,cand.weights_digest); self.assertEqual(ready.stages[-1].stage,"rollback-ready")
  executed=execute_rollback(rt,adm,rb,cp)
  final=extend_with_promotion(proof,cand,ev,prom,adm,executed)
  self.assertEqual(rt.model_digest,old); self.assertEqual(rt._current_model_digest(),old)
  self.assertEqual(final.stages[-1].stage,"rollback-executed"); self.assertEqual(final.stages[-1].subject_digest,old); self.assertEqual(len(final.stages),9)
