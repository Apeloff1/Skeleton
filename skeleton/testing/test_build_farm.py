import pytest
from skeleton.ai.build.build_farm import *


D = "0" * 64
E = "1" * 64


def worker(worker_id="w", env=D):
    return BuildWorker(
        worker_id,
        True,
        env,
        WorkerAttestation(worker_id, env, f"evidence-{worker_id}", True),
    )


def test_output_binds_job_worker_environment_and_attestation():
    artifact = execute(
        BuildFarmJob("j", D, D),
        worker(),
        lambda *args: b"out",
    )
    assert (
        artifact.job_id,
        artifact.worker_id,
        artifact.environment_digest,
        artifact.attestation_evidence,
    ) == ("j", "w", D, "evidence-w")


def test_boolean_attested_flag_is_insufficient():
    with pytest.raises(PermissionError):
        execute(
            BuildFarmJob("j", D, D),
            BuildWorker("w", True, D),
            lambda *args: b"x",
        )


def test_malformed_input_digest_rejected():
    with pytest.raises(ValueError):
        BuildFarmJob("j", "s", D)


def test_reproducible_build_requires_matching_independent_outputs():
    artifacts = execute_reproducible(
        BuildFarmJob("j", D, D),
        (worker("a", D), worker("b", E)),
        lambda *args: b"stable-output",
    )
    assert len({artifact.output_digest for artifact in artifacts}) == 1


def test_reproducible_build_detects_environment_sensitive_output():
    with pytest.raises(RuntimeError):
        execute_reproducible(
            BuildFarmJob("j", D, D),
            (worker("a", D), worker("b", E)),
            lambda source, build, env: env.encode(),
        )


def test_reproducibility_requires_distinct_workers():
    same = worker("a")
    with pytest.raises(ValueError):
        execute_reproducible(
            BuildFarmJob("j", D, D),
            (same, same),
            lambda *args: b"x",
        )
