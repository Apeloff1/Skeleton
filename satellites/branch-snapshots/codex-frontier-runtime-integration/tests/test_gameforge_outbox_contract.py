from skeleton.frontier.gameforge_outbox import BoundedOutbox


def test_outbox_is_bounded_and_peek_is_non_destructive():
    outbox = BoundedOutbox[int](2)
    assert outbox.append(1)
    assert outbox.append(2)
    assert not outbox.append(3)
    assert outbox.peek() == 1
    assert len(outbox) == 2
    assert outbox.remaining == 0
    assert outbox.pop() == 1
    assert outbox.peek() == 2


def test_outbox_rejects_bool_capacity():
    try:
        BoundedOutbox(True)
    except ValueError:
        pass
    else:
        raise AssertionError("boolean capacity must be rejected")
