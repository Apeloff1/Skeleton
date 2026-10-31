import pytest
from skeleton.frontier.worldsim.persistence import WorldLog, WorldReplayError
from skeleton.frontier.worldsim.navigation import NavGrid
from skeleton.frontier.worldsim.quality_arena import WorldCandidate, rank


def red(state, ev):
    state[ev["k"]] = state.get(ev["k"], 0) + ev["v"]
    return state


def test_log_checkpoint_replay_roundtrip():
    log, st = WorldLog({}, checkpoint_every=4), {}
    for i in range(10):
        st = log.append({"k": f"r{i % 3}", "v": i}, red, st)
    assert sorted(log.checkpoints) == [4, 8]
    assert log.replay(red) == st and log.verify(red)
    re = WorldLog.from_dict(log.to_dict())
    assert re.replay(red, 6) == log.replay(red, 6)
    re.checkpoints[8]["state"]["r0"] = -1
    with pytest.raises(WorldReplayError):
        re.replay(red)


def test_arena_ranks_reachable_varied_fast_world_first():
    good = WorldCandidate("good", NavGrid.from_rows(["...", "..."]), (0, 0), ((2, 1),), ("a", "b", "c"), 5.0)
    bad = WorldCandidate("bad", NavGrid.from_rows([".#.", ".#."]), (0, 0), ((2, 1),), ("a", "a", "a"), 50.0)
    out = rank([bad, good], budget_ms=10.0)
    assert [s.world_id for s in out] == ["good", "bad"]
    assert out[0].passed and set(out[1].failures) == {"unreachable_objectives", "over_budget"}
