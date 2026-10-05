from concurrent.futures import ThreadPoolExecutor

from skeleton.frontier.gameforge_idempotency import IdempotencyWindow


def test_concurrent_duplicate_records_have_one_winner():
    window = IdempotencyWindow[int](capacity=4)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda value: window.record("same", value), range(64)))
    winners = [value for accepted, value in results if accepted]
    assert len(winners) == 1
    assert window.lookup("same") == winners[0]
    assert window.stats().duplicates == 63


def test_none_is_a_valid_cached_value():
    window = IdempotencyWindow[None](capacity=1)
    assert window.record("empty", None) == (True, None)
    assert window.record("empty", "ignored") == (False, None)  # type: ignore[arg-type]
