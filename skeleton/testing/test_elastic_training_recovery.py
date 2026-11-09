from __future__ import annotations
import hashlib,pytest
from skeleton.training.elastic_recovery import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def coord():return ElasticCoordinator(TrainingEpoch("RUN.1",3,S("cp"),S("pos")))
def test_current_worker_fence_authorizes_write():c=coord();f=c.fence("WORKER.A");assert c.authorize_write(f)
def test_recovery_advances_epoch_and_invalidates_old_workers():
 c=coord();old=c.fence("WORKER.A");c.recover(ElasticResume(3,4,S("cp"),S("pos")))
 with pytest.raises(ElasticError,match="stale"):c.authorize_write(old)
def test_recovery_preserves_consumed_data_position():
 c=coord()
 with pytest.raises(ElasticError,match="mismatch"):c.recover(ElasticResume(3,4,S("cp"),S("other-pos")))
def test_stale_fence_token_rejected_after_refence():
 c=coord();old=c.fence("WORKER.A");new=c.fence("WORKER.A");assert c.authorize_write(new)
 with pytest.raises(ElasticError,match="stale"):c.authorize_write(old)
def test_epoch_cannot_skip_membership_generation():
 with pytest.raises(ElasticError,match="exactly one"):ElasticResume(3,5,S("cp"),S("pos"))
