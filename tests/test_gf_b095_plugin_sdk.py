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


def test_plugin_result_is_detached_from_mutable_plugin_owned_state():
    class SharedOutput:
        def __init__(self):
            self.value = {"items": [1]}

        def export(self, payload):
            return self.value

    plugin = SharedOutput()
    host = m.Host(frozenset())
    host.register(m.Manifest("shared", "exporter", (1, 0), ()), plugin)
    returned = host.call("shared", "export", {})
    plugin.value["items"].append(object())  # mutate after validation
    assert returned == {"items": [1]}
    assert returned is not plugin.value
    assert returned["items"] is not plugin.value["items"]


def test_host_rejects_malformed_scope_policy_before_registration():
    for bad in (["fs_read"], frozenset({"*"}), frozenset({"a" * 97}),
                frozenset(f"scope{i}" for i in range(129))):
        with pytest.raises(m.ContractError, match="scope policy"):
            m.Host(bad)


def test_conformance_validates_all_cases_before_any_plugin_dispatch():
    class CountingPlugin:
        calls = 0

        def export(self, payload):
            self.calls += 1
            return payload

    plugin = CountingPlugin()
    host = m.Host(frozenset())
    host.register(m.Manifest("safe", "exporter", (1, 0), ()), plugin)
    with pytest.raises(m.ContractError, match="unknown conformance plugin"):
        m.conformance(host, "missing", [])
    with pytest.raises(m.ContractError, match="invalid plugin conformance case"):
        m.conformance(host, "safe", [({}, lambda output: True), ({}, None)])
    assert plugin.calls == 0


def test_conformance_refuses_empty_or_late_invalid_cases_without_dispatch():
    class CountingPlugin:
        calls = 0

        def export(self, payload):
            self.calls += 1
            return payload

    plugin = CountingPlugin()
    host = m.Host(frozenset())
    host.register(m.Manifest("bounded", "exporter", (1, 0), ()), plugin)
    with pytest.raises(m.ContractError, match="conformance cases"):
        m.conformance(host, "bounded", [])
    with pytest.raises(m.ContractError, match="not canonical"):
        m.conformance(host, "bounded", [
            ({"n": 1}, lambda output: True),
            ({"n": object()}, lambda output: True),
        ])
    assert plugin.calls == 0
    assert m.conformance(host, "bounded", [({"n": 1}, lambda output: output["n"] == 1)])[
        "passed"
    ] is True
    assert plugin.calls == 2


def test_plugin_exception_diagnostics_do_not_escape_host_boundary():
    class Exploding:
        def export(self, payload):
            raise RuntimeError("secret-token-should-not-escape")

    host = m.Host(frozenset())
    host.register(m.Manifest("exploding", "exporter", (1, 0), ()), Exploding())
    with pytest.raises(m.ContractError, match="plugin execution failed") as exc:
        host.call("exploding", "export", {})
    assert "secret-token" not in str(exc.value)
    with pytest.raises(m.ContractError, match="unknown plugin"):
        host.call([], "export", {})
