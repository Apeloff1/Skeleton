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


def test_plugin_sdk_rejects_malformed_manifest_and_unbounded_payloads():
    for api in ((), (1,), (1, 0, 0), (True, 0), ("1", 0)):
        with pytest.raises(m.ContractError):
            m.Manifest("x", "exporter", api, ())
    with pytest.raises(m.ContractError):
        m.Manifest("../unsafe", "exporter", (1, 0), ())
    h = m.Host(frozenset())
    h.register(m.Manifest("e", "exporter", (1, 0), ()), Exp())
    for payload in ({"n": float("nan")}, {"n": object()}, {"n": "x" * 100_000}):
        with pytest.raises(m.ContractError):
            h.call("e", "export", payload)
    with pytest.raises(m.ContractError, match="conformance cases"):
        m.conformance(h, "e", [({"n": 1}, lambda x: True)] * 129)


def test_plugin_rejects_cyclic_and_oversized_nested_json_before_dispatch():
    h = m.Host(frozenset())
    h.register(m.Manifest("e", "exporter", (1, 0), ()), Exp())
    cycle = []
    cycle.append(cycle)
    for payload in ({"n": cycle}, {"n": [0] * 5000}, {"n": {"x": 10**2000}}):
        with pytest.raises(m.ContractError, match="bound|cyclic"):
            h.call("e", "export", payload)


def test_plugin_rejects_noncanonical_output_without_stringifying_objects():
    class Poison:
        def __str__(self):
            raise AssertionError("unsafe repr executed")

    class BadOutput:
        def export(self, payload):
            return {"out": Poison()}

    h = m.Host(frozenset())
    h.register(m.Manifest("bad", "exporter", (1, 0), ()), BadOutput())
    with pytest.raises(m.ContractError, match="not canonical"):
        h.call("bad", "export", {})
