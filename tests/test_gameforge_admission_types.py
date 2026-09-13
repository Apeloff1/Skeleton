import pytest

from skeleton.frontier.gameforge_admission import Admission, decide


def test_admission_prioritizes_read_only_then_background_shed():
    assert decide(background_allowed=False, read_only=True, active=99, limit=1, background=True) is Admission.READ_ONLY
    assert decide(background_allowed=False, read_only=False, active=0, limit=1, background=True) is Admission.SHED


def test_admission_rejects_non_boolean_flags():
    with pytest.raises(TypeError):
        decide(background_allowed=1, read_only=False, active=0, limit=1, background=False)
