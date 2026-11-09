from __future__ import annotations

import skeleton.jeeves.probabilistic as probabilistic


def test_probabilistic_facade_exports_joint_path_surface() -> None:
    expected = {
        "JointPathConfig",
        "JointPathForecast",
        "JointPathReport",
        "JointPathScenario",
        "JointPathStep",
        "ResidualPath",
        "energy_score",
        "evaluate_joint_paths",
        "forecast_joint_path",
        "validate_joint_path_report",
        "variogram_score",
    }
    assert expected.issubset(set(probabilistic.__all__))
    for name in expected:
        assert hasattr(probabilistic, name)
