"""A plane that has never been called is not a healthy zero-latency plane."""

import pytest

from skeleton.retrieval.plane_health import PlaneHealthTracker


def test_unknown_plane_has_no_health() -> None:
    health = PlaneHealthTracker()
    with pytest.raises(KeyError):
        health.state("rag")
    with pytest.raises(ValueError):
        health.record_success("  ", 1.0)
    health.record_success("rag", 12.0)
    assert health.state("rag").ewma_latency_ms == 12.0
    assert health.state("rag").attempts == 1
