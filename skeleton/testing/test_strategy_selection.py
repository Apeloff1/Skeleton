from skeleton.ai.strategy_selection import *
def test_disallowed_high_score_never_wins():
 d=select(StrategyConstraint(("safe",),5),(StrategySelection("unsafe",1,1),StrategySelection("safe",2,.5)));assert d.selected.name=="safe"
def test_no_eligible_strategy_abstains():assert select(StrategyConstraint(("safe",),1),(StrategySelection("safe",2,1),)).abstained
