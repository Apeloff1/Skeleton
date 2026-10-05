import hashlib
from dataclasses import replace

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.simulation import (
    SCENARIO_SCHEMA,
    Assumption,
    AssumptionSet,
    CounterfactualRolloutEngine,
    DeterministicEnvironmentAdapter,
    SimulationBoundaryError,
    SimulationRule,
    UncertaintyPropagationPolicy,
    WorldModelError,
)

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

@pytest.mark.parametrize(
    ("reward","terminal","uncertainty","match"),
    [
        (True, False, 0.1, "reward must be finite numeric"),
        (float("nan"), False, 0.1, "reward must be finite numeric"),
        (0.0, 1, 0.1, "terminal must be boolean"),
        (0.0, "false", 0.1, "terminal must be boolean"),
        (0.0, False, True, "uncertainty must be numeric"),
        (0.0, False, "0.1", "uncertainty must be numeric"),
    ],
)
def test_reducer_outputs_fail_closed_without_type_coercion(reward,terminal,uncertainty,match):
    def bad(state,action,seed):
        return state,reward,terminal,uncertainty
    env=DeterministicEnvironmentAdapter(simulation_id="strict",initial_state={},reducer=bad)
    with pytest.raises(SimulationBoundaryError,match=match):
        env.step({"x":1})
    assert env.state=={}


def test_environment_evidence_digests_use_shared_canonical_contract_bytes():
    env=DeterministicEnvironmentAdapter(simulation_id="digest",initial_state={"n":0},reducer=reducer,seed=7)
    transition=env.step({"add":1})
    assert transition.evidence.prior_state_digest==hashlib.sha256(canonical_json_bytes({"n":0})).hexdigest()
    assert transition.evidence.action_digest==hashlib.sha256(canonical_json_bytes({"add":1})).hexdigest()
    assert transition.evidence.next_state_digest==hashlib.sha256(canonical_json_bytes({"n":1})).hexdigest()


def test_simulation_mapping_keys_fail_closed_without_json_key_coercion():
    with pytest.raises(SimulationBoundaryError,match="deterministic JSON"):
        DeterministicEnvironmentAdapter(simulation_id="strict-keys",initial_state={1:"bad"},reducer=reducer)


def test_world_model_assumption_identity_uses_shared_canonical_contract_bytes():
    assumption=Assumption("a","model approximation",0.1,"test")
    expected={
        "schema":"skeleton.world_model_simulation.v1",
        "kind":"assumption",
        "assumption_id":"a",
        "statement":"model approximation",
        "uncertainty":0.1,
        "source_ref":"test",
    }
    assert assumption.digest==hashlib.sha256(canonical_json_bytes(expected)).hexdigest()


def test_scenario_rule_identity_uses_shared_canonical_contract_bytes():
    rule=SimulationRule("rule-1","bounded rule",{"limit":2},version=3)
    expected={
        "schema":SCENARIO_SCHEMA,
        "kind":"rule",
        "rule_id":"rule-1",
        "description":"bounded rule",
        "parameters":{"limit":2},
        "version":3,
    }
    assert rule.digest==hashlib.sha256(canonical_json_bytes(expected)).hexdigest()


def test_vol019_source_and_ai_simulation_mirrors_are_byte_identical():
    from pathlib import Path

    root=Path(__file__).resolve().parents[2]
    for relative in ("environment.py","world_model.py","scenario_runtime.py"):
        source=root/"skeleton"/"simulation"/relative
        mirror=root/"skeleton"/"ai"/"simulation"/relative
        assert source.read_bytes()==mirror.read_bytes()
