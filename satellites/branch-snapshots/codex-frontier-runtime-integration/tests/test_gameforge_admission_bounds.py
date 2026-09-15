import pytest

from skeleton.frontier.gameforge_admission import Admission, decide


def test_admission_rejects_boolean_concurrency_values():
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=True, limit=1, background=False)
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=0, limit=True, background=False)


def test_admission_preserves_read_only_precedence():
    assert decide(background_allowed=False, read_only=True, active=10, limit=1, background=True) is Admission.READ_ONLY
