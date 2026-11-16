"""Recovered canonical analytics and repair callback boundary regressions."""
from dataclasses import replace

import pytest

from skeleton.ai.game_builder.analytics.events import GameplayEvent,EventError
from skeleton.ai.game_builder.analytics.metrics import (
    build_sessions,stage_stats,difficulty_heatmap,DifficultyHeatmap,Funnel,
)
from skeleton.gameforge.batch_b039.self_repair import (
    Budget,EvalFailure,EvalResult,Mutation,RepairLoop,RouteChoice,
)


def event(player="p",session="s",seq=0,t=0,kind="level_start",day=0,level="level",enc=None):
    return GameplayEvent(player,session,seq,t,kind,day=day,level_id=level,encounter_id=enc)


def test_distinct_principals_cannot_merge_sessions_or_funnel_units():
    rows=[event("p","shared"),event("q","shared")]
    sessions=build_sessions(rows)
    assert len(sessions)==2 and {s.player for s in sessions}=={"p","q"}
    rows=[event("anon","p"),event("p","s")]
    result=Funnel(("level_start",)).run(rows)
    assert result.reached==(2,)


def test_exact_retry_deduplicated_conflicting_retry_denied():
    start=event()
    assert stage_stats([start,start])[("level",None)].attempts==1
    with pytest.raises(EventError):
        build_sessions([start,replace(start,t=1)])
    with pytest.raises(EventError):
        difficulty_heatmap([start,replace(start,day=1)])


def test_day_crossing_sequence_and_session_clocks_are_separate():
    first=event(session="first",seq=0,t=100,day=1)
    finish=event(session="second",seq=1,t=5,day=2,kind="level_complete")
    assert stage_stats([first,finish])[("level",None)].clear_times==[]
    a=event(seq=0,t=2,day=5)
    b=event(seq=1,t=1,day=6)
    with pytest.raises(EventError):
        build_sessions([a,b])
    b=replace(b,t=4)
    assert build_sessions([b,a])[0].duration==2


def test_death_only_cohort_cannot_bypass_minimum():
    rows=[event(kind="death",enc="boss")]
    result=difficulty_heatmap(rows,min_players=5)
    assert not result.cells and result.suppressed==2
    visible=difficulty_heatmap(rows,min_players=1)
    assert visible.cell("level","boss").deaths==1
    d=visible.to_dict()
    d["cells"][0]["players"]=0
    d["cells"][0]["low_confidence"]=True
    with pytest.raises(ValueError,match="zero-cohort"):
        DifficultyHeatmap.from_dict(d)


def test_unbounded_input_and_invalid_attrs_denied(monkeypatch):
    from itertools import repeat
    from skeleton.ai.game_builder.analytics import metrics
    monkeypatch.setattr(metrics,"MAX_METRIC_EVENTS",2)
    with pytest.raises(EventError,match="ceiling"):
        build_sessions(repeat(event()))
    from skeleton.ai.game_builder.analytics.events import clean_attrs
    with pytest.raises(EventError):
        clean_attrs({1:"x","good":"y"})
    with pytest.raises(EventError):
        clean_attrs([])
    with pytest.raises(EventError):
        GameplayEvent.from_dict({"player":"p","session_id":"s"})


class Clock:
    now=0
    def __call__(self):
        return self.now


def evaluate(a):
    n=a["nested"]["score"]
    return EvalResult(n,() if n>=10 else (EvalFailure("logic.score","too low"),))


def route(_):
    return RouteChoice("local","deterministic",0)


def test_late_candidate_never_promotes():
    clock=Clock()
    def late(a):
        if a["nested"]["score"]>=10:
            clock.now=5
        return evaluate(a)
    result=RepairLoop(late,lambda a,d,r:Mutation("nested",{"nested":{"score":10}},1),
                      route,Budget(3,2,5),clock).run({"nested":{"score":1}})
    assert result.status=="exhausted" and result.stop_reason=="time budget"
    assert result.artifact=={"nested":{"score":1}} and result.steps==1
    assert len(result.provenance)==1


def test_proposer_and_evaluator_cannot_mutate_incumbent():
    original={"nested":{"score":1}}
    def proposer(a,d,r):
        a["nested"]["score"]=99
        return Mutation("nested",{"nested":{"score":0}},0)
    def evaluator(a):
        result=evaluate(a)
        a["nested"]["score"]=100
        return result
    result=RepairLoop(evaluator,proposer,route,Budget(2,10,0),Clock()).run(original)
    assert result.artifact==original=={"nested":{"score":1}}


def test_route_cost_floor_holds_before_proposal():
    def forbidden(*a):
        pytest.fail("proposal executed beyond route floor")
    out=RepairLoop(evaluate,forbidden,lambda _:RouteChoice("m","local",2),
                   Budget(3,10,1),Clock()).run({"nested":{"score":1}})
    assert out.status=="exhausted" and out.steps==0


def test_clock_rewind_after_route_is_rejected():
    clock=Clock()
    clock.now=5
    def rewind(_):
        clock.now=4
        return route(None)
    with pytest.raises(ValueError,match="monotonically"):
        RepairLoop(evaluate,lambda *a:None,rewind,Budget(3,10,1),clock).run({"nested":{"score":0}})
