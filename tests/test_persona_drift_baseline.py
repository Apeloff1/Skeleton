"""An empty persona sample must clear the baseline instead of dividing by zero."""

from skeleton.memory.drift import PersonaDriftDetector


def test_empty_baseline_clears_without_error() -> None:
    detector = PersonaDriftDetector()
    detector.establish_baseline(["answer", "tool"])
    detector.establish_baseline([])
    for _ in range(12):
        detector.record("answer")
    assert detector.check_drift() is None
    assert detector.get_profile()["baseline_established"] is False
