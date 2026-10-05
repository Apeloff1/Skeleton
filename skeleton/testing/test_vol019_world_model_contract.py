import pytest
from dataclasses import replace
from skeleton.simulation import Assumption, AssumptionSet, CounterfactualRolloutEngine, DeterministicEnvironmentAdapter, SimulationBoundaryError, UncertaintyPropagationPolicy, WorldModelError

def reducer(state,action,seed):
    n=int(state.get("n",0))+int(action["add"])
    return {"n":n},float(n),n>=2,0.2

def engine():
    env=DeterministicEnvironmentAdapter(simulation_id="sim",initial_state={"n":0},reducer=reducer,seed=7)
    assumptions=AssumptionSet((Assumption("a","model approximation",0.1,"test"),))
    return CounterfactualRolloutEngine(env,assumptions=assumptions,max_steps=4,max_cases=3)

def test_rollout_is_deterministic_and_simulation_only():
    a=engine().rollout(({"add":1},{"add":1}))
    b=engine().rollout(({"add":1},{"add":1}))
    assert a.digest==b.digest and a.terminal
    assert not a.can_support_real_world_fact and not a.can_satisfy_real_postcondition
    with pytest.raises(WorldModelError): a.require_real_world_postcondition_authority()

def test_uncertainty_is_monotonic_and_binds_assumptions():
    r=engine().rollout(({"add":1},{"add":1}))
    assert r.steps[0].cumulative_uncertainty>=0.1
    assert r.steps[1].cumulative_uncertainty>=r.steps[0].cumulative_uncertainty
    assert r.assumption_set_digest==engine().assumptions.digest

def test_counterfactual_order_is_canonical():
    e=engine(); a=e.compare({"z":({"add":1},),"a":({"add":2},)})
    e=engine(); b=e.compare({"a":({"add":2},),"z":({"add":1},)})
    assert [(x.case_id,x.digest) for x in a]==[(x.case_id,x.digest) for x in b]

def test_step_budget_fails_before_adapter_effect():
    e=engine()
    with pytest.raises(WorldModelError): e.rollout(({"add":1},)*5)
    assert e.adapter.state=={"n":0}

def test_nonfinite_adapter_uncertainty_fails_closed():
    def bad(state,action,seed): return state,0.0,False,float("nan")
    env=DeterministicEnvironmentAdapter(simulation_id="bad",initial_state={},reducer=bad)
    with pytest.raises(SimulationBoundaryError): CounterfactualRolloutEngine(env).rollout(({"x":1},))

def test_transition_evidence_identity_tamper_is_rejected():
    base=DeterministicEnvironmentAdapter(simulation_id="sim",initial_state={"n":0},reducer=reducer,seed=7)
    class Tamper:
        simulation_id="sim"; seed=7
        @property
        def state(self): return base.state
        def reset(self): return base.reset()
        def step(self,action):
            t=base.step(action)
            return replace(t,evidence=replace(t.evidence,simulation_id="other"))
    with pytest.raises(WorldModelError): CounterfactualRolloutEngine(Tamper()).rollout(({"add":1},))

def test_uncertainty_policy_rejects_bool_and_out_of_range():
    p=UncertaintyPropagationPolicy()
    for v in (True,-0.1,1.1,float("inf")):
        with pytest.raises(WorldModelError): p.combine(0.1,v)
