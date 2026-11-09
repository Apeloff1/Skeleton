"""Media studio ↔ LAFS publish — port of gameforge-rs media_studio.rs."""

from __future__ import annotations

import hashlib

import pytest

from skeleton.forge.lafs import Lafs
from skeleton.forge.media_studio import (
    DEFAULT_PIPELINE,
    JobStatus,
    MediaStudio,
    MediaStudioError,
    StudioJob,
    decide_pipeline,
)
from skeleton.kernel.saga import SagaLedger, Status as SagaStatus


@pytest.fixture()
def studio() -> MediaStudio:
    return MediaStudio()


@pytest.fixture()
def ledger() -> SagaLedger:
    return SagaLedger()


@pytest.fixture()
def lafs() -> Lafs:
    return Lafs()


def test_decide_pipeline_full_and_kinds():
    assert decide_pipeline("hero.mp4") == list(DEFAULT_PIPELINE)
    assert decide_pipeline("poster.png", kind="image") == [
        "ingest",
        "thumbnail",
        "publish",
    ]
    assert decide_pipeline("vo.wav", kind="audio") == [
        "ingest",
        "waveform",
        "publish",
    ]
    with pytest.raises(MediaStudioError, match="asset ref"):
        decide_pipeline("  ")


def test_submit_stages_job_and_opens_saga(studio: MediaStudio, ledger: SagaLedger):
    job = studio.submit(ledger, "clip-a", ["ingest", "publish"])
    assert isinstance(job, StudioJob)
    assert job.asset == "clip-a"
    assert job.pipeline == ["ingest", "publish"]
    assert job.status is JobStatus.STAGED
    assert job.output is None
    assert job.saga_id.startswith("studio:")
    saga = ledger.get(job.saga_id)
    assert saga.status is SagaStatus.PENDING
    assert len(saga.steps) == 2
    assert studio.get(job.id) is not None
    assert len(studio.list()) == 1


def test_submit_uses_decide_pipeline_when_omitted(
    studio: MediaStudio, ledger: SagaLedger
):
    job = studio.submit(ledger, "still-1", kind="image")
    assert job.pipeline == ["ingest", "thumbnail", "publish"]


def test_advance_then_publish_to_lafs(
    studio: MediaStudio, ledger: SagaLedger, lafs: Lafs
):
    job = studio.submit(ledger, "out/hero.bin", ["ingest", "publish"])
    mid = studio.advance(ledger, job.id)
    assert mid is not None
    assert mid.status is JobStatus.RUNNING
    done = studio.advance(ledger, job.id)
    assert done is not None
    assert done.status is JobStatus.DONE
    saga = ledger.get(job.saga_id)
    assert saga.status is SagaStatus.COMPLETED
    assert saga.context["completed_stages"] == ["ingest", "publish"]

    payload = b"finished-asset-bytes"
    result = studio.publish_to_lafs(job.id, lafs, payload)
    assert result is not None
    published, manifest = result
    assert published.output == "out/hero.bin"
    assert manifest.name == "out/hero.bin"
    assert lafs.read_manifest("out/hero.bin") == payload
    digest = hashlib.sha256(payload).hexdigest()
    assert manifest.chunks == [digest]


def test_publish_manifest_name_only_when_done(
    studio: MediaStudio, ledger: SagaLedger
):
    job = studio.submit(ledger, "asset-x", ["ingest"])
    assert studio.publish(job.id, "asset-x") is None  # still staged
    assert studio.advance(ledger, job.id) is not None
    published = studio.publish(job.id, "asset-x-final")
    assert published is not None
    assert published.output == "asset-x-final"
    assert studio.publish(job.id, "again") is not None  # idempotent attach ok


def test_run_batch_completes_and_lafs_publish(
    studio: MediaStudio, ledger: SagaLedger, lafs: Lafs
):
    job = studio.submit(ledger, "batch.bin", list(DEFAULT_PIPELINE))
    finished = studio.run(ledger, job.id)
    assert finished is not None
    assert finished.status is JobStatus.DONE
    assert ledger.get(job.saga_id).status is SagaStatus.COMPLETED
    result = studio.publish_to_lafs(
        job.id, lafs, b"full-pipeline", name="batch-out"
    )
    assert result is not None
    pub, _ = result
    assert pub.output == "batch-out"
    assert lafs.read_manifest("batch-out") == b"full-pipeline"


def test_fail_compensates_completed_stages(
    studio: MediaStudio, ledger: SagaLedger
):
    job = studio.submit(
        ledger, "fail-me", ["ingest", "transcode", "publish"]
    )
    assert studio.advance(ledger, job.id) is not None  # ingest done
    failed = studio.fail(ledger, job.id)
    assert failed is not None
    assert failed.status is JobStatus.COMPENSATED
    saga = ledger.get(job.saga_id)
    assert saga.status is SagaStatus.COMPENSATED
    assert saga.context.get("compensated_stages") == ["ingest"]
    # no further advance / publish
    assert studio.advance(ledger, job.id) is None
    assert studio.publish_to_lafs(job.id, Lafs(), b"x") is None


def test_publish_to_lafs_refuses_before_done(
    studio: MediaStudio, ledger: SagaLedger, lafs: Lafs
):
    job = studio.submit(ledger, "early", ["ingest", "publish"])
    assert studio.publish_to_lafs(job.id, lafs, b"nope") is None


def test_unknown_job_ops_return_none(studio: MediaStudio, ledger: SagaLedger):
    assert studio.advance(ledger, "missing") is None
    assert studio.fail(ledger, "missing") is None
    assert studio.publish("missing", "x") is None
    assert studio.get("missing") is None
