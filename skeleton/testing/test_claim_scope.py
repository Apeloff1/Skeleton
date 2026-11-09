import pytest
from skeleton.ai.claim_scope import *
def s(pop):return ClaimScope((ScopeDimension("population",pop),ScopeDimension("year","2026")))
def test_population_mismatch_is_first_class():
 r=compare_scope(s("adult"),s("child"));assert not r.compatible and r.conflicts==("population",)
def test_unqualified_comparison_fails():
 with pytest.raises(ValueError):require_compatible(s("adult"),s("child"))

def test_missing_scope_dimension_requires_qualification():
 a=ClaimScope((ScopeDimension("region","NO"),));b=ClaimScope((ScopeDimension("region","NO"),ScopeDimension("time","now")))
 assert not compare_scope(a,b).compatible and "time" in compare_scope(a,b).conflicts

def test_empty_scope_and_whitespace_dimension_rejected():
 import pytest
 with pytest.raises(ValueError):ClaimScope(())
 with pytest.raises(ValueError):ClaimScope((ScopeDimension(" ","x"),))
