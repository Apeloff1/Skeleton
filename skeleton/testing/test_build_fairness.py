from skeleton.automation.build_fairness import Lane,order
def test_age_can_overcome_priority():assert order((Lane("old",1,20,0),Lane("new",10,0,0)))[0].id=="old"
