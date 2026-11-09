from skeleton.gameforge.batch_b073 import GridWorld, PlaytestAgent


def test_reaches_goal_and_path_replays():
    w = GridWorld(["S..", ".#.", "..G"])
    agent = PlaytestAgent(w, seed=3)
    rep = agent.run()
    assert rep.ok and len(rep.goal_path) == 4
    assert agent.replay(rep.goal_path) == w.goal


def test_reports_softlock_with_path():
    w = GridWorld(["SX", ".G"])
    rep = PlaytestAgent(w).run()
    soft = [f for f in rep.findings if f.kind == "softlock"]
    assert soft and PlaytestAgent(w).replay(soft[0].path) == (0, 1)


def test_reports_unreachable_goal():
    rep = PlaytestAgent(GridWorld(["S#G"])).run()
    assert not rep.reached_goal
    assert any(f.kind == "unreachable_goal" for f in rep.findings)


def test_invariant_flags_exploit():
    class Leaky(GridWorld):
        def step(self, s, a):
            if s == (0, 0) and a == "E":
                return (0, 2)  # teleports through the wall
            return super().step(s, a)

    w = Leaky(["S#G"])
    w.actions = lambda s: ["E"] if s == (0, 0) else []
    rep = PlaytestAgent(w, invariants=(
        lambda s, a, n: "teleport" if abs(n[1] - s[1]) > 1 else None,)).run()
    assert any(f.kind == "exploit" and f.path == ("E",) for f in rep.findings)


def test_deterministic_for_seed():
    w = GridWorld(["S...", "....", "...G"])
    assert PlaytestAgent(w, seed=9).run().goal_path == PlaytestAgent(w, seed=9).run().goal_path
