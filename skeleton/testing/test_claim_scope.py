import pytest
from skeleton.ai.claim_scope import *
def s(pop):return ClaimScope((ScopeDimension("population",pop),ScopeDimension("year","2026")))
def test_population_mismatch_is_first_class():
 r=compare_scope(s("adult"),s("child"));assert not r.compatible and r.conflicts==("population",)
def test_unqualified_comparison_fails():
 with pytest.raises(ValueError):require_compatible(s("adult"),s("child"))
