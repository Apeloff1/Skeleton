from core.shift_supervisor.constants import MANAGER_DEFAULT_INTERVAL_SECONDS, SECRETARY_DEFAULT_INTERVAL_SECONDS


def test_requested_cadences_are_exact():
    assert SECRETARY_DEFAULT_INTERVAL_SECONDS == 15 * 60
    assert MANAGER_DEFAULT_INTERVAL_SECONDS == 30 * 60
