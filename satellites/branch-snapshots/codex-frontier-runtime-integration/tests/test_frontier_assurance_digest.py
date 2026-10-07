from skeleton.frontier.assurance.digest import state_digest


def test_state_digest_is_order_stable():
    assert state_digest({"a": 1, "b": 2}) == state_digest({"b": 2, "a": 1})
    assert state_digest({"a": 1}) != state_digest({"a": 2})
