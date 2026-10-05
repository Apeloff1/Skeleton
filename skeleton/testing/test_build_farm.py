import pytest
from skeleton.ai.build.build_farm import *
D="0"*64
def worker():return BuildWorker("w",True,D,WorkerAttestation("w",D,"evidence",True))
def test_output_binds_job_worker_environment_and_attestation():
 a=execute(BuildFarmJob("j",D,D),worker(),lambda *x:b"out");assert (a.job_id,a.worker_id,a.environment_digest,a.attestation_evidence)==("j","w",D,"evidence")
def test_boolean_attested_flag_is_insufficient():
 with pytest.raises(PermissionError):execute(BuildFarmJob("j",D,D),BuildWorker("w",True,D),lambda *x:b"x")
def test_malformed_input_digest_rejected():
 with pytest.raises(ValueError):execute(BuildFarmJob("j","s",D),worker(),lambda *x:b"x")
