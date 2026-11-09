from skeleton.ai.strategy_selection import *
def test_disallowed_high_score_never_wins():
 d=select(StrategyConstraint(("safe",),5),(StrategySelection("unsafe",1,1),StrategySelection("safe",2,.5)));assert d.selected.name=="safe"
def test_no_eligible_strategy_abstains():assert select(StrategyConstraint(("safe",),1),(StrategySelection("safe",2,1),)).abstained

def test_unproven_strategy_cannot_be_selected():assert select(StrategyConstraint(("x",),10),(StrategySelection("x",1,1,False),)).abstained
def test_nonfinite_cost_cannot_win():
 import math
 assert select(StrategyConstraint(("x",),10),(StrategySelection("x",math.nan,1),)).abstained

def test_duplicate_strategy_candidates_rejected():
 import pytest
 x=StrategySelection("s",1,1,True)
 with pytest.raises(ValueError):select(StrategyConstraint(("s",),2),(x,x))
