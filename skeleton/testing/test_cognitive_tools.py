from skeleton.ai.runtime.deferred.cognitive_tools import *
V=StrategyVersion("tree","1")
def test_strategy_requires_eval_evidence_for_production():
 assert not production_eligible(CognitiveStrategy(V,()))
 assert production_eligible(CognitiveStrategy(V,(StrategyEvidence("b",True,1),)))
def test_selection_stays_in_allowed_set_budget_or_abstains():
 s=CognitiveStrategy(V,(StrategyEvidence("b",True,2),))
 assert select_strategy(StrategySelection((s,),StrategyConstraint(frozenset({V}),1))).abstained
 assert select_strategy(StrategySelection((s,),StrategyConstraint(frozenset({V}),2))).selected==V
def test_cost_accounting_contains_metadata_not_reasoning_content():
 c=ReasoningCost("op",V,"m","1",ReasoningStage.PLAN,3)
 a=attribute_cost((c,));assert a.total_units==3 and not hasattr(c,"content")
def test_static_analysis_is_deterministic_and_located():
 a=analyze_plan("v1",("a",),(("a","missing"),),())
 b=analyze_plan("v1",("a",),(("a","missing"),),())
 assert a==b and a.diagnostics[0].location and a.diagnostics[0].remediation
def test_simulation_is_non_production_and_includes_failure_modes():
 s=simulate_plan(("x",));assert not s.production_evidence
 assert {x.scenario for x in s.steps}=={"success","failure","timeout","resource_exhaustion"}
def test_tool_composition_cannot_union_authority():
 a=ToolBinding("a","1",frozenset({"read","write"}),"A","B","verified")
 b=ToolBinding("b","1",frozenset({"read"}),"B","C","verified")
 assert not compose_tools(ToolComposition((a,b),frozenset({"read","write"}))).admissible
 assert compose_tools(ToolComposition((a,b),frozenset({"read"}))).effective_authority==frozenset({"read"})
def test_tool_composition_checks_schema_and_trust_transitions():
 a=ToolBinding("a","1",frozenset({"read"}),"A","B","verified")
 b=ToolBinding("b","1",frozenset({"read"}),"X","C","verified")
 assert not compose_tools(ToolComposition((a,b),frozenset({"read"}))).admissible


def test_simulation_evidence_is_explicitly_non_production():
 simulation=simulate_plan(("step",))
 assert simulation.production_evidence is False
