from __future__ import annotations
import hashlib,pytest
from skeleton.training.checkpointing import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def cp():
 m=CheckpointManifest(S("model"),S("opt"),S("sched"),S("rng"),S("data-pos"),S("cfg"),2);return TrainingCheckpoint("CHECKPOINT.1","RUN.1",m,S("artifact"))
def resume(c):return ResumeState(c.checkpoint_id,c.manifest.digest,c.manifest.config_digest,c.artifact_digest)
def test_complete_checkpoint_validates_semantically_equivalent_resume():c=cp();assert validate_resume(c,resume(c),{2})
def test_optimizer_state_is_part_of_manifest_identity():c=cp();m=CheckpointManifest(c.manifest.model_digest,S("different"),c.manifest.scheduler_digest,c.manifest.rng_digest,c.manifest.data_position_digest,c.manifest.config_digest,2);assert m.digest!=c.manifest.digest
def test_config_drift_rejected():
 c=cp();r=ResumeState(c.checkpoint_id,c.manifest.digest,S("other"),c.artifact_digest)
 with pytest.raises(CheckpointError,match="configuration"):validate_resume(c,r,{2})
def test_partial_or_corrupted_artifact_rejected():
 c=cp();r=ResumeState(c.checkpoint_id,c.manifest.digest,c.manifest.config_digest,S("partial"))
 with pytest.raises(CheckpointError,match="integrity"):validate_resume(c,r,{2})
def test_unknown_checkpoint_schema_rejected():
 c=cp()
 with pytest.raises(CheckpointError,match="schema"):validate_resume(c,resume(c),{1})
