import pytest
from skeleton.ai.build.build_farm import *
def test_output_binds_job_worker_environment():
 a=execute(BuildFarmJob("j","s","b"),BuildWorker("w",True,"env"),lambda *x:b"out");assert (a.job_id,a.worker_id,a.environment_digest)==("j","w","env")
def test_unattested_worker_rejected():
 with pytest.raises(PermissionError):execute(BuildFarmJob("j","s","b"),BuildWorker("w",False,"e"),lambda *x:b"x")
