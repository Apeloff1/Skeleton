import unittest
from dataclasses import replace
from skeleton.ai.training.project_learning import ProjectOutcome,LearningApproval,admit_project_outcome
from skeleton.ai.training.project_learning_run import build_project_learning_manifest
from skeleton.ai.training.lifecycle_proof import LifecycleProof,LifecycleProofError,LifecycleStage,prove_project_learning

D="a"*64
def chain():
 o=ProjectOutcome("out","tenant","project",D,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"successful")
 a=LearningApproval(o.digest,"reviewer","1"*64,"2"*64,"3"*64,"project-learning",True)
 ad=admit_project_outcome(o,a,dataset_id="dataset",source_id="project:out")
 run=build_project_learning_manifest(ad,run_id="run",base_model_digest=D,code_digest="b"*64,config_digest="c"*64,seed_manifest_digest="d"*64,max_steps=100,scope="project-learning")
 return o,a,ad,run

class TestLifecycleProof(unittest.TestCase):
 def test_complete_learning_authority_chain_is_hash_linked(self):
  outcome,approval,admission,run=chain()
  p=prove_project_learning("cycle-1",outcome,approval,admission,run)
  self.assertEqual([s.stage for s in p.stages],["successful-project-outcome","explicit-learning-approval","dataset-admission","candidate-training-run"])
  self.assertEqual(p.stages[-1].subject_digest,run.manifest.digest)
  self.assertEqual(len(p.digest),64)
 def test_outcome_substitution_rejected(self):
  o,a,ad,r=chain()
  with self.assertRaises(LifecycleProofError): prove_project_learning("x",replace(o,output_digest="9"*64),a,ad,r)
 def test_approval_substitution_rejected(self):
  o,a,ad,r=chain()
  with self.assertRaises(LifecycleProofError): prove_project_learning("x",o,replace(a,transform_digest="9"*64),ad,r)
 def test_admission_substitution_rejected(self):
  o,a,ad,r=chain()
  with self.assertRaises(LifecycleProofError): prove_project_learning("x",o,a,replace(ad,approval_digest="9"*64),r)
 def test_broken_predecessor_chain_rejected(self):
  p=prove_project_learning("x",*chain())
  broken=replace(p.stages[-1],previous_digest="9"*64)
  with self.assertRaises(LifecycleProofError): LifecycleProof("x",p.stages[:-1]+(broken,))
 def test_replayed_stage_rejected(self):
  p=prove_project_learning("x",*chain())
  with self.assertRaises(LifecycleProofError): LifecycleProof("x",p.stages+(p.stages[-1],))
 def test_non_successful_outcome_rejected_even_with_reused_receipts(self):
  o,a,ad,r=chain()
  with self.assertRaises(LifecycleProofError): prove_project_learning("x",replace(o,status="candidate"),a,ad,r)

if __name__=="__main__": unittest.main()
