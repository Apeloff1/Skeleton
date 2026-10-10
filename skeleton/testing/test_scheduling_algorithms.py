from skeleton.ai.scheduling import *
def w(i,auth=("worker",)):return {"id":i,"authorities":auth}
def t(i,**kw):return {"id":i,"authority":"worker","lease":True,"sequence":0,**kw}
def test_dependency_runs_before_child():
 r=schedule((t("b",dependencies=("a",)),t("a")),(w("w"),));assert [x.task_id for x in r.assignments]==["a","b"]
def test_missing_lease_or_authority_never_optimized_into_assignment():
 r=schedule((t("a",lease=False),t("b",authority="admin")),(w("w"),));assert r.assignments==() and r.deferred==("a","b")
def test_deadline_policy_is_replaceable_and_measurable():
 tasks=(t("late",deadline=10,sequence=0),t("early",deadline=1,sequence=1))
 assert [x.task_id for x in schedule(tasks,(w("w"),),policy=SchedulingPolicy.FIFO).assignments]==["late","early"]
 assert [x.task_id for x in schedule(tasks,(w("w"),),policy=SchedulingPolicy.EARLIEST_DEADLINE).assignments]==["early","late"]

def test_deferred_prerequisite_blocks_dependent():
 tasks=({"id":"a","dependencies":(),"authority":"x","lease":False,"sequence":0},{"id":"b","dependencies":("a",),"authority":"x","lease":True,"sequence":1})
 s=schedule(tasks,({"id":"w","authorities":("x",)},));assert not s.assignments and set(s.deferred)=={"a","b"}
