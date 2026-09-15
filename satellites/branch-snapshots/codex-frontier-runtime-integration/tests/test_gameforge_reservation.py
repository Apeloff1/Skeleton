import pytest

from skeleton.frontier.gameforge_reservation import Reservation


def test_reservation_identity_is_immutable():
    reservation = Reservation("request-1", 0)
    assert reservation.request_id == "request-1"
    assert reservation.sequence == 0
    with pytest.raises(Exception):
        reservation.sequence = 1


def test_reservation_rejects_invalid_identity():
    with pytest.raises(ValueError):
        Reservation("", 0)
    with pytest.raises(ValueError):
        Reservation("r", -1)
