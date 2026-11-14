from skeleton.frontier.gameforge_observability import Observation

def test_observation_is_immutable_and_validated():
    item = Observation("queue.depth", 2, "items")
    assert item.value == 2
    try:
        item.name = "other"
    except Exception:
        pass
    else:
        raise AssertionError("observation must be immutable")

def test_observation_rejects_empty_labels():
    for args in (("", 1), ("x", 1, "")):
        try:
            Observation(*args)
        except ValueError:
            continue
        raise AssertionError("invalid observation accepted")
