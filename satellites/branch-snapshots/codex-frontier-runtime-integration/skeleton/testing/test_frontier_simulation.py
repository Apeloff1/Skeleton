from skeleton.frontier.simulation import GenerationRequest, SimulationTick, stable_seed


def test_stable_seed_is_reproducible_and_bounded():
    first = stable_seed("world", "alpha")
    assert first == stable_seed("world", "alpha")
    assert 0 <= first < 2**64


def test_simulation_tick_is_immutable_and_accumulative():
    tick = SimulationTick(0, 42, {"population": 10})
    next_tick = tick.next(delta={"population": 2, "energy": 5})
    assert tick.tick == 0
    assert next_tick.tick == 1
    assert next_tick.state == {"population": 12, "energy": 5}


def test_generation_request_validates_identity():
    try:
        GenerationRequest("", "prompt", 1)
    except ValueError:
        pass
    else:
        raise AssertionError("empty generation kind must fail")
