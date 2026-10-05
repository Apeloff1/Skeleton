from skeleton.ai.build.impact_analysis import *
def test_known_dependency_propagates_owner_and_test():
 r=analyze_impact(ImpactQuery(("a",)),(("architecture",{"a":("b",)},True),),{"b":"team"}, {"b":("test_b",)})
 assert r.affected==("a","b") and r.owners==("team",) and r.tests==("test_b",) and r.uncertainty==0
def test_missing_graph_completeness_is_exposed_not_hidden():
 r=analyze_impact(ImpactQuery(("a",)),(("trace",{},False),),{},{});assert r.uncertainty==1 and not r.evidence[0].complete

def test_duplicate_changed_identity_rejected():
 import pytest
 with pytest.raises(ValueError):analyze_impact(ImpactQuery(("a","a")),(),{}, {})
