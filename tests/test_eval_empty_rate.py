"""An eval that ran nothing did not pass."""

from skeleton.intelligence.eval_framework import EvalSuite


def test_filtered_suite_is_not_a_perfect_score(tmp_path) -> None:
    suite = EvalSuite("empty", root=tmp_path)
    suite.case("nightly", {"x": 1}, lambda output: True, tags=["nightly"])
    report = suite.run(lambda payload: payload, tags=["smoke"])
    assert report["ran"] == 0
    assert report["pass_rate"] == 0.0
