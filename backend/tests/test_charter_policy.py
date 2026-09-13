import pytest

from core.charter_policy import CharterPolicy, Rule


def test_uncharted_domain_fails_closed():
    gate = CharterPolicy()
    decision = gate.decide("build", "build.execute", 999)
    assert decision.permitted is False
    assert decision.cited_rule is None
    assert "no charter" in decision.reason


def test_missing_action_fails_closed():
    gate = CharterPolicy()
    gate.ratify("build", [Rule(id="read", action="build.read")])
    assert gate.decide("build", "build.execute", 999).permitted is False


def test_weight_gate_and_quorum_metadata():
    gate = CharterPolicy()
    gate.ratify(
        "build",
        [Rule(id="execute", action="build.execute", min_weight=5, requires_quorum=True)],
    )
    denied = gate.decide("build", "build.execute", 4)
    allowed = gate.decide("build", "build.execute", 5)
    assert denied.permitted is False
    assert denied.cited_rule == "execute"
    assert denied.quorum_required is True
    assert allowed.permitted is True
    assert allowed.quorum_required is True


def test_edict_replaces_action_rule_deterministically():
    gate = CharterPolicy()
    charter = gate.ratify("runtime", [Rule(id="old", action="runtime.deploy", min_weight=9)])
    edict = gate.propose_edict(
        "runtime",
        Rule(id="new", action="runtime.deploy", min_weight=3),
        "court",
    )
    assert edict is not None
    assert gate.decide("runtime", "runtime.deploy", 3).permitted is False
    assert gate.enforce_edict(edict.id) is True
    decision = gate.decide("runtime", "runtime.deploy", 3)
    assert decision.permitted is True
    assert decision.cited_rule == "new"
    assert charter.amendments == 1


def test_enforce_is_idempotent():
    gate = CharterPolicy()
    charter = gate.ratify("assets", [Rule(id="r1", action="assets.read")])
    edict = gate.propose_edict("assets", Rule(id="r2", action="assets.write"), "operator")
    assert edict is not None
    assert gate.enforce_edict(edict.id) is True
    assert gate.enforce_edict(edict.id) is True
    assert charter.amendments == 1


def test_invalid_charter_inputs_rejected():
    gate = CharterPolicy()
    with pytest.raises(ValueError, match="domain"):
        gate.ratify("", [])
    with pytest.raises(ValueError, match="negative"):
        gate.ratify("x", [Rule(id="bad", action="x.run", min_weight=-1)])
    with pytest.raises(ValueError, match="duplicate action"):
        gate.ratify("x", [Rule(id="a", action="x.run"), Rule(id="b", action="x.run")])


def test_negative_actor_weight_never_passes():
    gate = CharterPolicy()
    gate.ratify("x", [Rule(id="a", action="x.run", min_weight=0)])
    assert gate.decide("x", "x.run", -1).permitted is False
