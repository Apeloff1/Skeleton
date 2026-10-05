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


def test_cognitive_controls_fail_closed_on_invalid_identity():
 import pytest
 bad=CognitiveStrategy(StrategyVersion("","v1"),(StrategyEvidence("bench",True,1),))
 assert not production_eligible(bad)
 with pytest.raises(ValueError): select_strategy(StrategySelection((),StrategyConstraint(frozenset(),-1)))
 with pytest.raises(ValueError): attribute_cost((ReasoningCost("op",StrategyVersion("s","v"),"m","mv",ReasoningStage.PLAN,-1),))
 incomplete=ToolBinding("tool","v",frozenset({"read"}),"","out","trusted")
 assert not compose_tools(ToolComposition((incomplete,),frozenset({"read"}))).admissible
 binding=ToolBinding("tool","v",frozenset({"read"}),"in","out","trusted")
 assert not compose_tools(ToolComposition((binding,binding),frozenset({"read"}))).admissible


def test_plan_analysis_and_simulation_require_deterministic_identity():
 import pytest
 with pytest.raises(ValueError): analyze_plan("",("a",),(),())
 with pytest.raises(ValueError): analyze_plan("ir",(),(),())
 with pytest.raises(ValueError): analyze_plan("ir",("a",),(),(PlanLintRule("","v1"),))
 with pytest.raises(ValueError): analyze_plan("ir",("a",),(),(PlanLintRule("r","v1"),PlanLintRule("r","v1")))
 with pytest.raises(ValueError): simulate_plan(())
 with pytest.raises(ValueError): simulate_plan(("a","a"))


def test_plan_analysis_reports_dependency_cycles():
 result=analyze_plan("ir-v1",("a","b","c"),(("a","b"),("b","c"),("c","a")),(PlanLintRule("base","v1"),))
 assert any(d.rule_id=="cycle" and d.severity is Severity.ERROR for d in result.diagnostics)
 acyclic=analyze_plan("ir-v1",("a","b"),(("a","b"),),(PlanLintRule("base","v1"),))
 assert not any(d.rule_id=="cycle" for d in acyclic.diagnostics)
