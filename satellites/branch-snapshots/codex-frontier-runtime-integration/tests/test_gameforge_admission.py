import pytest

from skeleton.frontier.gameforge_admission import Admission, accepted, decide, degraded


def test_admission_fails_closed():
    assert decide(background_allowed=True, read_only=True, active=0, limit=4, background=False) is Admission.READ_ONLY
    assert decide(background_allowed=False, read_only=False, active=0, limit=4, background=True) is Admission.SHED
    assert decide(background_allowed=True, read_only=False, active=4, limit=4, background=False) is Admission.SHED
    assert decide(background_allowed=True, read_only=False, active=0, limit=4, background=False) is Admission.ACCEPT


def test_admission_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=-1, limit=1, background=False)
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=0, limit=0, background=False)
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=True, limit=1, background=False)
    with pytest.raises(ValueError):
        decide(background_allowed=True, read_only=False, active=0, limit=True, background=False)


def test_admission_rejects_non_boolean_flags():
    with pytest.raises(TypeError):
        decide(background_allowed=1, read_only=False, active=0, limit=1, background=False)
    with pytest.raises(TypeError):
        decide(background_allowed=True, read_only=0, active=0, limit=1, background=False)
    with pytest.raises(TypeError):
        decide(background_allowed=True, read_only=False, active=0, limit=1, background=0)


def test_admission_classification_helpers_are_total():
    assert accepted(Admission.ACCEPT)
    assert not accepted(Admission.SHED)
    assert degraded(Admission.SHED)
    assert degraded(Admission.READ_ONLY)
    assert not degraded(Admission.ACCEPT)
    with pytest.raises(TypeError):
        accepted("accept")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        degraded("shed")  # type: ignore[arg-type]
