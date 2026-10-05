from skeleton.frontier.gameforge_priority import Priority,higher

def test_priority_order_is_explicit():
    assert higher(Priority.INTERACTIVE,Priority.BACKGROUND)
    assert higher(Priority.BACKGROUND,Priority.BULK)
    assert not higher(Priority.BULK,Priority.INTERACTIVE)
