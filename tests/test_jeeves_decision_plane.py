import pytest
from skeleton.jeeves.decision import *

def d():
 c=(Criterion("quality",.6),Criterion("cost",.4))
 o=(Option("a","first",(("quality",.9),("cost",.7))),Option("b","second",(("quality",.6),("cost",.9))))
 return Decision("select a bounded option",DecisionClass.OPERATIONAL,o,c,assumptions=("inputs are bounded",))

def test_scores_and_guard():
 x=d(); assert score_option(x.options[0],x.criteria)>.7; assert inspect(x).allowed

def test_duplicate_options_rejected():
 with pytest.raises(ValueError): Decision("q",DecisionClass.INFORMATIONAL,(Option("a","x"),Option("a","y")),(Criterion("quality"),))

def test_commit_is_host_controlled():
 x=d(); blocked=Decision(x.question,x.classification,x.options,x.criteria,DecisionState.COMMITTED,x.assumptions); assert not inspect(blocked).allowed

def test_audit_chain():
 a=DecisionAudit(); x=d(); a.append(x.id,AuditKind.CREATED,"draft"); a.append(x.id,AuditKind.REVIEWED,"review"); assert a.verify()


def test_generated_decision_rule_catalogs_are_valid_and_deterministic():
    from skeleton.jeeves.decision.policy import PolicyKind, RULES as POLICY_RULES
    from skeleton.jeeves.decision.provenance import (
        ProvenanceKind,
        RULES as PROVENANCE_RULES,
    )
    from skeleton.jeeves.decision.scoring import ScoringKind, RULES as SCORING_RULES

    catalogs = (
        (POLICY_RULES, PolicyKind, 240, "policy"),
        (PROVENANCE_RULES, ProvenanceKind, 180, "provenance"),
        (SCORING_RULES, ScoringKind, 220, "scoring"),
    )
    for rules, kind_type, expected_count, prefix in catalogs:
        assert len(rules) == expected_count
        assert rules[0].name == f"{prefix}_001"
        assert rules[-1].name == f"{prefix}_{expected_count:03d}"
        assert rules[0].threshold == 0.01
        assert rules[99].threshold == 0.0
        assert all(isinstance(rule.kind, kind_type) for rule in rules)
        assert {rule.kind for rule in rules} == set(kind_type)
