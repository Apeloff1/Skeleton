import pytest
from skeleton.ai.critical_path import analyze_critical_path
def test_known_answer_path_and_slack():
 r=analyze_critical_path({"a":2,"b":3,"c":1},(("a","b"),("a","c")))
 assert r.duration==5 and r.task_ids==("a","b")
 assert next(x for x in r.slack if x.task_id=="c").latest_start-next(x for x in r.slack if x.task_id=="c").earliest_start==2
def test_duration_change_recomputes_path():
 assert analyze_critical_path({"a":2,"b":1},(("a","b"),)).duration==3
 assert analyze_critical_path({"a":4,"b":1},(("a","b"),)).duration==5
def test_cycle_or_missing_dependency_rejected():
 with pytest.raises(ValueError):analyze_critical_path({"a":1,"b":1},(("a","b"),("b","a")))
 with pytest.raises(ValueError):analyze_critical_path({"a":1},(("a","x"),))
def test_real_blocker_state_is_surfaced():
 r=analyze_critical_path({"a":1},(),{"a":"lease unavailable"});assert r.blockers[0].reason=="lease unavailable"

def test_nan_and_boolean_durations_rejected():
 import pytest,math
 with pytest.raises(ValueError):analyze_critical_path({"a":math.nan},())
 with pytest.raises(ValueError):analyze_critical_path({"a":True},())
