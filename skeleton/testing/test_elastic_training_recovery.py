import pytest
from skeleton.learning.elastic_training import *
def test_epoch_fence_rejects_stale_workers_and_binds_resume_cursor():
 r=ElasticRecovery("run"); r.begin_epoch(sequence=1,checkpoint_digest="a"*64,dataset_cursor_digest="b"*64); f=r.fence("w"); r.require_current(f); r.begin_epoch(sequence=2,checkpoint_digest="c"*64,dataset_cursor_digest="d"*64)
 with pytest.raises(ElasticRecoveryError): r.require_current(f)
 assert r.resume_identity()==("c"*64,"d"*64)
