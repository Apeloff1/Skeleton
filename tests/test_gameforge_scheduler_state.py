from skeleton.frontier.gameforge_scheduler import Scheduler


def test_scheduler_exposes_size_and_resets():
    scheduler = Scheduler({"a": 2, "b": 1})
    assert scheduler.size == 3
    assert scheduler.cursor == 0
    assert [scheduler.next(), scheduler.next(), scheduler.next()] == ["a", "a", "b"]
    assert scheduler.cursor == 0
    scheduler.next()
    scheduler.reset()
    assert scheduler.cursor == 0
    assert scheduler.next() == "a"
