import hashlib

import pytest

from skeleton.data.ingestion import (
    IngestedRecord,
    IngestionEngine,
    IngestionError,
    IngestionJob,
    QuarantineRecord,
)


def _job(payload: bytes, **overrides) -> IngestionJob:
    values = dict(
        job_id="job-1",
        source_id="source-1",
        source_digest=hashlib.sha256(payload).hexdigest(),
        acquired_at_ns=1,
        rights="licensed",
        classification="internal",
        parser_version="v1",
        trusted_source=True,
    )
    values.update(overrides)
    return IngestionJob(**values)


def test_idempotent_replay_returns_original_outcome() -> None:
    engine = IngestionEngine()
    payload = b"x"
    first = engine.ingest(_job(payload), payload, parser=lambda _: {"x": 1})
    second = engine.ingest(_job(payload), payload, parser=lambda _: {"x": 2})
    assert first == second
    assert isinstance(first, IngestedRecord)


def test_untrusted_source_is_quarantined() -> None:
    payload = b"x"
    result = IngestionEngine().ingest(
        _job(payload, trusted_source=False),
        payload,
        parser=lambda _: {"x": 1},
    )
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "untrusted_source"


@pytest.mark.parametrize(
    "override",
    [
        {"rights": "other"},
        {"classification": "restricted"},
        {"parser_version": "v2"},
        {"trusted_source": False},
        {"acquired_at_ns": 2},
    ],
)
def test_job_authority_rebind_fails(override) -> None:
    engine = IngestionEngine()
    payload = b"a"
    engine.ingest(_job(payload), payload, parser=lambda _: {"x": 1})
    with pytest.raises(IngestionError, match="authority cannot be rebound"):
        engine.ingest(_job(payload, **override), payload, parser=lambda _: {"x": 2})


def test_noncanonical_parser_output_is_quarantined() -> None:
    payload = b"a"
    result = IngestionEngine().ingest(
        _job(payload),
        payload,
        parser=lambda _: {"nan": float("nan")},
    )
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "parser_output_not_canonical"
