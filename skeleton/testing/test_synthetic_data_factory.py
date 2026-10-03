import math

import pytest

from skeleton.data.synthetic import (
    SyntheticDataError,
    SyntheticDataFactory,
    SyntheticJob,
)


def _factory() -> SyntheticDataFactory:
    return SyntheticDataFactory(
        SyntheticJob("job", "generator", "v1", "a" * 64, "dataset")
    )


def test_synthetic_origin_and_quality_gates() -> None:
    factory = _factory()
    first = factory.record(
        record_id="a",
        value={"x": 1},
        group_label="g1",
        parent_refs=["parent"],
    )
    factory.record(
        record_id="b",
        value={"x": 1},
        group_label="g1",
        parent_refs=["parent"],
    )
    quality = factory.evaluate(
        reference_content_digests=[first.content_digest],
        valid_record_ids=["a", "b"],
        min_diversity=0.8,
        max_memorization=0.1,
        max_group_share=0.8,
    )
    assert first.origin == "synthetic"
    assert quality.promotion_allowed is False
    assert quality.memorization_ratio == 1.0


def test_noncanonical_record_is_rejected() -> None:
    with pytest.raises(SyntheticDataError, match="canonical JSON"):
        _factory().record(
            record_id="a",
            value={"x": math.nan},
            group_label="g1",
            parent_refs=["parent"],
        )


@pytest.mark.parametrize("threshold", [math.nan, math.inf, -0.1, 1.1, True])
def test_invalid_quality_thresholds_fail(threshold) -> None:
    factory = _factory()
    factory.record(
        record_id="a",
        value={"x": 1},
        group_label="g1",
        parent_refs=["parent"],
    )
    with pytest.raises(SyntheticDataError):
        factory.evaluate(
            reference_content_digests=[],
            valid_record_ids=["a"],
            min_diversity=threshold,
        )


def test_reference_digest_must_be_canonical_sha256() -> None:
    factory = _factory()
    factory.record(
        record_id="a",
        value={"x": 1},
        group_label="g1",
        parent_refs=["parent"],
    )
    with pytest.raises(SyntheticDataError, match="reference content digest"):
        factory.evaluate(
            reference_content_digests=["not-a-digest"],
            valid_record_ids=["a"],
        )
