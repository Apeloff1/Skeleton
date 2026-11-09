from skeleton.cognition.arbiter import Arbiter, Candidate
from skeleton.cognition.checkpoint import CheckpointManager
from skeleton.cognition.ensemble import Ensemble, Vote
from skeleton.cognition.guard import GuardChain
from skeleton.cognition.transaction import StateTransaction


def test_arbiter_respects_risk_and_cost():
    d = Arbiter(risk_limit=.5, budget=2).decide([
        Candidate("unsafe", 1, 1, risk=.9), Candidate("cheap", .8, .7, cost=1)
    ])
    assert d.action == "cheap"
    assert "unsafe" in d.rejected


def test_transaction_rolls_back_failed_invariant():
    tx = StateTransaction({"n": 1}, invariants={"positive": lambda s: s["n"] > 0})
    tx.set("n", -1)
    result = tx.commit()
    assert not result.committed
    assert tx.state["n"] == 1


def test_checkpoint_digest_and_restore():
    manager = CheckpointManager()
    manager.save("x", {"value": 7})
    out = {}
    manager.restore("x", lambda payload: out.update(payload))
    assert out == {"value": 7}
    assert manager.names() == ("x",)


def test_guards_fail_closed():
    guards = GuardChain({"type": lambda x: isinstance(x, int), "positive": lambda x: x > 0})
    assert guards.evaluate(2).allowed
    assert not guards.evaluate(-1).allowed
    assert not guards.evaluate("x").allowed


def test_ensemble_weights_confidence():
    result = Ensemble().combine([Vote("a", .9), Vote("b", 1.0), Vote("a", .8)])
    assert result.value == "a"
    assert result.support == 2
