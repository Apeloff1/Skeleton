from skeleton.school.policy_calibration import PolicyCalibrator


def test_sparse_policy_evidence_is_shrunk_toward_neutral() -> None:
    calibrator = PolicyCalibrator()
    calibrator.observe("challenge", reward=1.0, successful=True)

    reliability = calibrator.reliability("challenge")

    assert 0.5 < reliability < 0.7


def test_reliability_converges_with_repeated_success() -> None:
    calibrator = PolicyCalibrator()
    for _ in range(20):
        calibrator.observe("transfer", reward=1.0, successful=True)

    assert calibrator.reliability("transfer") > 0.85
