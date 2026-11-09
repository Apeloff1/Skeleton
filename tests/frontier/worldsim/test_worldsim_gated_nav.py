from skeleton.frontier.worldsim.navigation import NavGrid, GateSpec, gated_reachable, detect_softlocks


def test_gate_needs_key():
    g = NavGrid.from_rows(["....."])
    locked = GateSpec(gates={(3, 0): "red"})
    assert (4, 0) not in gated_reachable(g, locked, (0, 0))
    keyed = GateSpec(gates={(3, 0): "red"}, keys={(1, 0): "red"})
    assert (4, 0) in gated_reachable(g, keyed, (0, 0))


def test_one_way_drop_without_key_is_softlock():
    # start (0,0); one-way (1,0)->(2,0); key at (0,1) back side; exit gate (4,0)
    g = NavGrid.from_rows([".....", ".####"])
    spec = GateSpec(gates={(4, 0): "k"}, keys={(0, 1): "k"}, one_way=frozenset({((1, 0), (2, 0))}))
    rep = detect_softlocks(g, spec, (0, 0), [(4, 0)])
    assert rep["goal_reachable"] and not rep["ok"]
    assert (2, 0) in rep["softlock_cells"] and (4, 0) not in rep["softlock_cells"]


def test_no_softlock_when_all_paths_can_finish():
    g = NavGrid.from_rows(["...."])
    rep = detect_softlocks(g, GateSpec(), (0, 0), [(3, 0)])
    assert rep["ok"] and rep["softlock_cells"] == []
