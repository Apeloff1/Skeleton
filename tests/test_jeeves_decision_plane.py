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
