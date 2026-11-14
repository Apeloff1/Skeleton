from skeleton.frontier.gameforge_reservation_book import ReservationBook


def test_duplicate_owner_survives_full_capacity():
    book = ReservationBook(1)
    first = book.add("r1")
    duplicate = book.add("r1")
    assert duplicate == first
    assert book.full
    assert book.add("r2") is None
    assert book.get("r1") == first
