from skeleton.frontier.gameforge_reservation_book import ReservationBook


def test_reservation_book_is_bounded_and_idempotent():
    book = ReservationBook(1)
    first = book.add("r1")
    assert first.sequence == 0
    assert book.add("r1") == first
    assert book.add("r2") is None
    assert book.contains("r1")
    assert book.remove("r1") == first
    second = book.add("r2")
    assert second.sequence == 1
    assert book.remaining == 0
