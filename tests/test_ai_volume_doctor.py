"""AI shard doctor. No tree read."""

from skeleton.ai.volume_doctor import claim_full, doctor


def test_shard() -> None:
    body = doctor()
    assert body["lines"] == 7650009
    assert body["full_tree"] is False
    assert body["sample_mass"] == 1.0392


def test_full_refused() -> None:
    try:
        claim_full(1)
    except RuntimeError:
        return
    raise AssertionError("partial tree claimed")
