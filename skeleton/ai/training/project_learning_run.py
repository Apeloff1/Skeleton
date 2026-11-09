"""Build candidate-only FLGB-07 manifests from explicitly admitted project outcomes."""
from __future__ import annotations
from dataclasses import dataclass
from .flgb_training_runtime import TrainingManifest, require_digest, require_id
from .project_learning import ProjectTrainingAdmission, ProjectLearningError

@dataclass(frozen=True)
class ProjectLearningRun:
    admission_digest:str
    manifest:TrainingManifest
    def __post_init__(self):
        require_digest(self.admission_digest,"admission_digest")
        if self.manifest.output_kind!="candidate-only": raise ProjectLearningError("project learning must remain candidate-only")

def build_project_learning_manifest(
    admission:ProjectTrainingAdmission,*,run_id:str,base_model_digest:str,
    code_digest:str,config_digest:str,seed_manifest_digest:str,max_steps:int,scope:str,
)->ProjectLearningRun:
    if not isinstance(admission,ProjectTrainingAdmission): raise ProjectLearningError("ProjectTrainingAdmission required")
    if not admission.rights.permits(scope): raise ProjectLearningError("dataset rights do not permit requested training scope")
    manifest=TrainingManifest(
        require_id(run_id,"run_id"),require_digest(base_model_digest,"base_model_digest"),
        (admission.revision.digest,),require_digest(code_digest,"code_digest"),
        require_digest(config_digest,"config_digest"),require_digest(seed_manifest_digest,"seed_manifest_digest"),
        max_steps,"candidate-only",
    )
    return ProjectLearningRun(admission.digest,manifest)

__all__=["ProjectLearningRun","build_project_learning_manifest"]
