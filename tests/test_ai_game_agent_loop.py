import pytest

from skeleton.ai.game_builder.agent_loop import (
    AuthoritativeGameState, GameLoop, Mutation, Outcome, Rule, StaleVersionError,
    StateMutationError, WinLossDetector)


def _hp_validator(data, _m):
    if data.get("hp", 0) < 0:
        raise StateMutationError("hp negative")


def make_state(**kw):
    return AuthoritativeGameState({"turn": 0, "hp": 10, "score": 0, "seed": 7},
                                  validators=[_hp_validator], protected_keys=frozenset({"seed"}), **kw)


class Climber:
    def __init__(self, delta=3):
        self.delta = delta
    def reason(self, obs):
        return {"gain": self.delta}
    def act(self, plan, snap):
        return {"score": snap.get("score") + plan["gain"]}


class Bleeder:
    def reason(self, obs):
        return "hurt"
    def act(self, plan, snap):
        return {"hp": snap.get("hp") - 4}


class Cheater:
    def reason(self, obs):
        try:
            obs["seed"] = 1
        except TypeError:
            pass
        return "cheat"
    def act(self, plan, snap):
        return {"seed": 99}


# --- state protection ---------------------------------------------------
def test_snapshot_is_read_only():
    s = make_state()
    snap = s.snapshot()
    with pytest.raises(TypeError):
        snap.data["hp"] = 0
    assert s.snapshot().get("hp") == 10


def test_nested_snapshot_frozen():
    s = AuthoritativeGameState({"inv": {"items": [1, 2]}})
    snap = s.snapshot()
    with pytest.raises(TypeError):
        snap.data["inv"]["items"] = []
    assert snap.data["inv"]["items"] == (1, 2)


def test_apply_bumps_version_and_history():
    s = make_state()
    out = s.apply(Mutation(0, {"score": 5}, "t", "why"))
    assert out.version == 1 == s.version
    assert s.history[-1][:3] == (1, "t", "why")
    assert out.digest != s.history[0][3]


def test_stale_version_rejected():
    s = make_state()
    s.apply(Mutation(0, {"score": 1}))
    with pytest.raises(StaleVersionError):
        s.apply(Mutation(0, {"score": 2}))
    assert s.snapshot().get("score") == 1


def test_validator_rejection_leaves_state():
    s = make_state()
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {"hp": -1}))
    assert s.version == 0 and s.snapshot().get("hp") == 10


def test_protected_keys_and_empty_and_type():
    s = make_state()
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {"seed": 1}))
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {}))
    with pytest.raises(StateMutationError):
        s.apply({"score": 1})  # type: ignore[arg-type]


def test_mutation_input_not_aliased():
    s = make_state()
    payload = {"bag": [1]}
    s.apply(Mutation(0, payload))
    payload["bag"].append(2)
    assert s.snapshot().get("bag") == (1,)


# --- WinLossDetector -----------------------------------------------------
def test_detector_win_loss_ongoing_draw():
    d = WinLossDetector.threshold("score", win_at=10, lose_at=-1, max_turns=5)
    s = make_state()
    assert d.evaluate(s.snapshot())[0] is Outcome.ONGOING
    s.apply(Mutation(0, {"score": 10}))
    assert d.evaluate(s.snapshot())[0] is Outcome.WIN
    s.apply(Mutation(1, {"score": -1}))
    assert d.evaluate(s.snapshot())[0] is Outcome.LOSS
    s.apply(Mutation(2, {"score": 0, "turn": 5}))
    assert d.evaluate(s.snapshot()) == (Outcome.DRAW, "max_turns")


def test_detector_loss_precedes_win():
    d = WinLossDetector([Rule("w", Outcome.WIN, lambda s: True), Rule("l", Outcome.LOSS, lambda s: True)])
    assert d.evaluate(make_state().snapshot()) == (Outcome.LOSS, "l")


def test_detector_broken_rule_ignored():
    d = WinLossDetector([Rule("boom", Outcome.WIN, lambda s: 1 / 0)])
    assert d.evaluate(make_state().snapshot())[0] is Outcome.LOSS


# --- loop ------------------------------------------------------------------
def test_loop_runs_to_win():
    s = make_state()
    loop = GameLoop(s, Climber(), WinLossDetector.threshold("score", win_at=9))
    assert loop.run() is Outcome.WIN
    assert [st.turn for st in loop.steps] == [0, 1, 2]
    assert all(st.accepted and st.verified for st in loop.steps)
    assert s.snapshot().get("turn") == 3


def test_loop_loss_via_hp_and_validator():
    s = make_state()
    d = WinLossDetector([Rule("dead", Outcome.LOSS, lambda sn: sn.get("hp") <= 2)])
    loop = GameLoop(s, Bleeder(), d)
    assert loop.run() is Outcome.LOSS
    assert s.snapshot().get("hp") == 2


def test_loop_cheater_cannot_touch_protected_state():
    s = make_state()
    loop = GameLoop(s, Cheater(), WinLossDetector(), max_rejections=2)
    assert loop.run() is Outcome.LOSS
    assert s.snapshot().get("seed") == 7 and s.version == 0
    assert all(not st.accepted and "rejected" in st.note for st in loop.steps)


def test_loop_draw_by_turn_cap_and_terminal_step():
    s = make_state()
    loop = GameLoop(s, Climber(0), WinLossDetector(max_turns=3))
    assert loop.run() is Outcome.DRAW
    assert loop.steps[-1].version_before == loop.steps[-1].version_after


def test_loop_verify_failure_counts():
    s = make_state()
    loop = GameLoop(s, Climber(), WinLossDetector(), verify=lambda b, a, p: False, max_rejections=2)
    assert loop.run() is Outcome.LOSS
    assert len(loop.steps) == 1 and not loop.steps[0].verified and loop.held

def test_canonical_state_rejects_nonfinite_object_and_cycle_before_publish():
    import math
    from dataclasses import dataclass
    for payload in ({"x":float("nan")}, {"x":object()}, {"x":{1,2}}, {"x":1<<300}):
        with pytest.raises(StateMutationError):
            AuthoritativeGameState(payload)
    s=make_state()
    old=s.snapshot()
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {"hp":float("inf")}))
    assert s.snapshot()==old and s.history[-1][0]==0
    cycle=[]
    cycle.append(cycle)
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {"extra":cycle}))
    assert s.version==0


def test_validator_cannot_mutate_nested_candidate_or_forge_success():
    def mutate(data, _):
        data["nested"]["hp"]=999
    s=AuthoritativeGameState({"turn":0,"nested":{"hp":10}},validators=[mutate])
    with pytest.raises(StateMutationError):
        s.apply(Mutation(0, {"turn":1}))
    assert s.version==0 and s.snapshot().data["nested"]["hp"]==10


def test_nested_verifier_refuses_incorrect_values():
    from skeleton.ai.game_builder.agent_loop.loop import _default_verify
    s=AuthoritativeGameState({"turn":0,"nested":{"a":[1]}})
    b=s.snapshot()
    a=s.apply(Mutation(0,{"nested":{"a":[2]}}))
    assert _default_verify(b,a,{"nested":{"a":[2]}})
    assert not _default_verify(b,a,{"nested":{"a":[999]}})


def test_agent_forged_turn_does_not_commit():
    class Forger:
        def reason(self,obs): return None
        def act(self,plan,snap): return {"turn":9999,"score":999}
    s=make_state()
    game=GameLoop(s,Forger(),WinLossDetector(),max_rejections=1)
    assert game.run()==Outcome.LOSS
    assert s.version==0 and s.snapshot().get("score")==0


def test_postcommit_verifier_failure_holds_without_fake_rollback():
    s=make_state()
    game=GameLoop(s,Climber(),WinLossDetector(),verify=lambda a,b,c: False)
    assert game.run()==Outcome.LOSS
    assert s.version==1 and game.held
    assert game.step().outcome==Outcome.LOSS and s.version==1


def test_loop_rejects_invalid_step_caps():
    s=make_state()
    with pytest.raises(StateMutationError):GameLoop(s,Climber(),WinLossDetector(),max_rejections=0)
    loop=GameLoop(s,Climber(),WinLossDetector())
    for n in (0,True,-1,10001):
        with pytest.raises(StateMutationError):loop.run(n)


def test_terminal_threshold_nonfinite_and_broken_rule_hold():
    for x in (float("nan"),float("inf")):
        with pytest.raises(StateMutationError):
            WinLossDetector.threshold("score",win_at=x)
    detector=WinLossDetector([Rule("unavailable",Outcome.WIN,lambda s: 1/0)])
    assert detector.evaluate(make_state().snapshot())[0] is Outcome.LOSS
