import pytest
from skeleton.gameforge.batch_b09x import b095_plugin_sdk as m


class Exp:
    def export(self, p):
        return {"out": p["n"] * 2}


def test_register_and_conformance():
    h = m.Host(frozenset({"fs_read"}))
    h.register(m.Manifest("e", "exporter", (1, 0), ("fs_read",)), Exp())
    r = m.conformance(h, "e", [({"n": 2}, lambda o: o["out"] == 4)])
    assert r == {"plugin": "e", "passed": True, "cases": 1}


def test_rejections():
    h = m.Host(frozenset())
    with pytest.raises(m.ContractError):
        h.register(m.Manifest("e", "exporter", (1, 0), ("net",)), Exp())
    with pytest.raises(m.ContractError):
        h.register(m.Manifest("t", "tool", (1, 0), ()), Exp())
    with pytest.raises(m.ContractError):
        m.Manifest("e", "exporter", (2, 0), ())
    h.register(m.Manifest("e", "exporter", (1, 0), ()), Exp())
    with pytest.raises(m.ContractError):
        h.call("e", "run", {})
    with pytest.raises(m.ContractError):
        h.call("nope", "export", {})


def test_duplicate_and_nondeterministic_plugins():
    import itertools

    h = m.Host(frozenset())
    h.register(m.Manifest("e", "exporter", (1, 0), ()), Exp())
    with pytest.raises(m.ContractError):
        h.register(m.Manifest("e", "exporter", (1, 0), ()), Exp())
    counter = itertools.count()

    class Flaky:
        def export(self, p):
            return {"n": next(counter)}

    h.register(m.Manifest("f", "exporter", (1, 0), ()), Flaky())
    assert m.conformance(h, "f", [({}, lambda o: True)])["passed"] is False
