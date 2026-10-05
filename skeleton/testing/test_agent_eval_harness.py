from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.agent_eval_harness import AgentEvalError,AgentEvaluationReport,AgentScenario,AgentScenarioResult,evaluate_agent

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def test_agent_eval_binds_scenarios_to_performance_evidence():
    scenarios=(AgentScenario("s1","resolve task",("tool.read",),3),)
    results=(AgentScenarioResult("s1","agent",2,True,(),d("perf-case")),)
    report=evaluate_agent(agent_id="agent",scenarios=scenarios,results=results,performance_evidence_digest=d("perf"))
    assert report.passed is True
    assert report.promotion_authority is False
    assert len(report.digest)==64

def test_action_budget_overrun_is_rejected():
    with pytest.raises(AgentEvalError,match="action budget"):
        evaluate_agent(
            agent_id="agent",
            scenarios=(AgentScenario("s","task",("x",),1),),
            results=(AgentScenarioResult("s","agent",2,True,(),d("e")),),
            performance_evidence_digest=d("p"),
        )

def test_success_cannot_hide_policy_violations():
    with pytest.raises(AgentEvalError,match="successful scenario"):
        AgentScenarioResult("s","agent",1,True,("POLICY",),d("e"))

def test_report_cannot_claim_promotion_authority():
    result=AgentScenarioResult("s","agent",1,True,(),d("e"))
    with pytest.raises(AgentEvalError,match="cannot grant"):
        AgentEvaluationReport("agent",(result,),True,d("p"),True)
