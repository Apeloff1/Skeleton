"""A polish loop does not turn a bad round count into one pass."""

import pytest

from skeleton.forge.forge_quality import persist_quality, polish_loop


def test_bad_rounds_and_a_missing_row_are_refused() -> None:
    with pytest.raises(ValueError):
        polish_loop({}, max_rounds=True)
    with pytest.raises(ValueError):
        polish_loop({}, max_rounds=0)
    with pytest.raises(ValueError):
        polish_loop({}, stage_floor_grade=-1)
    with pytest.raises(ValueError):
        persist_quality(None)
    result = polish_loop({"title": "demo"}, max_rounds=1, persist=False)
    assert result["rounds"] == 1
    assert result["accepted"] is False
