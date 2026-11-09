import unittest
from skeleton.ai.training.project_learning import ProjectOutcome,LearningApproval,admit_project_outcome,ProjectLearningError
from skeleton.ai.training.project_learning_run import build_project_learning_manifest
D="a"*64
class TestProjectLearningRun(unittest.TestCase):
 def admission(self):
  o=ProjectOutcome("o","t","p",D,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64,"successful")
  a=LearningApproval(o.digest,"reviewer","1"*64,"2"*64,"3"*64,"project-learning",True)
  return admit_project_outcome(o,a,dataset_id="dataset",source_id="project:o")
 def test_manifest_is_candidate_only_and_binds_admitted_revision(self):
  a=self.admission()
  r=build_project_learning_manifest(a,run_id="run",base_model_digest=D,code_digest="b"*64,config_digest="c"*64,seed_manifest_digest="d"*64,max_steps=100,scope="project-learning")
  self.assertEqual(r.manifest.output_kind,"candidate-only")
  self.assertEqual(r.manifest.dataset_revision_digests,(a.revision.digest,))
  self.assertEqual(r.admission_digest,a.digest)
 def test_scope_escalation_fails_closed(self):
  with self.assertRaises(ProjectLearningError):
   build_project_learning_manifest(self.admission(),run_id="run",base_model_digest=D,code_digest="b"*64,config_digest="c"*64,seed_manifest_digest="d"*64,max_steps=1,scope="foundation-pretraining")

if __name__=="__main__": unittest.main()
