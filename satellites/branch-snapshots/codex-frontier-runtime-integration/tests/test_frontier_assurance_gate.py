import pytest

from skeleton.frontier.assurance.gate import QualityGate


def test_quality_gate_requires_all_checks():
    assert QualityGate.from_checks([True, True]).passed
    assert not QualityGate.from_checks([True, False]).passed
    with pytest.raises(RuntimeError):
        QualityGate.from_checks([False]).require()
