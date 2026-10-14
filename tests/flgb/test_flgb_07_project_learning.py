import unittest
from dataclasses import replace
from skeleton.ai.training.project_learning import ProjectOutcome,LearningApproval,ProjectLearningError,admit_project_outcome

D=("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64)
def outcome(status="successful"):
 return ProjectOutcome("outcome","tenant","project",*D,status)
def approval(o,approved=True,scope="project-learning"):
 return LearningApproval(o.digest,"human-reviewer","1"*64,"2"*64,"3"*64,scope,approved)

class TestProjectLearningAdmission(unittest.TestCase):
 def test_successful_explicitly_approved_outcome_becomes_dataset_revision(self):
  o=outcome(); a=approval(o); x=admit_project_outcome(o,a,dataset_id="project-dataset",source_id="project:outcome")
  self.assertTrue(x.rights.permits("project-learning"))
  self.assertEqual(x.revision.content_digest,o.content_digest)
  self.assertEqual(x.revision.rights_digest,x.rights.digest)
  self.assertEqual(x.outcome_digest,o.digest)
 def test_ordinary_candidate_cannot_self_train(self):
  o=outcome("candidate")
  with self.assertRaises(ProjectLearningError): admit_project_outcome(o,approval(o),dataset_id="d",source_id="s")
 def test_rejected_outcome_cannot_train(self):
  o=outcome("rejected")
  with self.assertRaises(ProjectLearningError): admit_project_outcome(o,approval(o),dataset_id="d",source_id="s")
 def test_success_without_explicit_approval_cannot_train(self):
  o=outcome()
  with self.assertRaises(ProjectLearningError): admit_project_outcome(o,approval(o,False),dataset_id="d",source_id="s")
 def test_approval_cannot_be_replayed_across_outcomes(self):
  first=outcome(); second=replace(first,output_digest="9"*64)
  with self.assertRaises(ProjectLearningError): admit_project_outcome(second,approval(first),dataset_id="d",source_id="s")
 def test_dataset_content_is_approved_artifact_not_knowledge_root(self):
  o=outcome(); x=admit_project_outcome(o,approval(o),dataset_id="d",source_id="s")
  self.assertEqual(x.revision.content_digest,o.content_digest)
  self.assertNotEqual(x.revision.content_digest,o.knowledge_root_digest)
 def test_rights_scope_is_explicit_and_narrow(self):
  o=outcome(); x=admit_project_outcome(o,approval(o,scope="adapter-only"),dataset_id="d",source_id="s")
  self.assertTrue(x.rights.permits("adapter-only"))
  self.assertFalse(x.rights.permits("project-learning"))

if __name__=="__main__": unittest.main()
