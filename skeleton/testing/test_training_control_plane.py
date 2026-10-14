from __future__ import annotations
import hashlib,pytest
from skeleton.training.control_plane import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def cfg():return TrainingConfig("CFG.1","DATASET.1","MODEL.1",S("hp"))
def admission(c):return TrainingAdmission("ADMISSION.1",c.digest,4,1,1024,100)
def plane():return TrainingControlPlane(("DATASET.1",),("MODEL.1",))
def test_registered_inputs_and_resource_admission_create_durable_run():
 c=cfg();r=plane().admit("RUN.1",c,admission(c));assert r.state is RunState.ADMITTED
def test_unregistered_dataset_fails_closed():
 c=cfg()
 with pytest.raises(TrainingError,match="unregistered"):TrainingControlPlane((),("MODEL.1",)).admit("RUN.1",c,admission(c))
def test_admission_is_exactly_bound_to_config():
 c=cfg();bad=TrainingAdmission("ADMISSION.1",S("other"),1,0,1,1)
 with pytest.raises(TrainingError,match="mismatch"):plane().admit("RUN.1",c,bad)
def test_checkpoint_state_requires_persisted_digest():
 c=cfg();p=plane();p.admit("RUN.1",c,admission(c));p.transition("RUN.1",RunState.RUNNING)
 with pytest.raises(TrainingError,match="checkpoint"):p.transition("RUN.1",RunState.CHECKPOINTED)
def test_terminal_run_requires_evidence_and_cannot_resurrect():
 c=cfg();p=plane();p.admit("RUN.1",c,admission(c));p.transition("RUN.1",RunState.RUNNING);p.transition("RUN.1",RunState.SUCCEEDED,evidence_digest=S("e"))
 with pytest.raises(TrainingError,match="illegal"):p.transition("RUN.1",RunState.RUNNING)
