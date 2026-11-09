import pytest
from skeleton.automation.build_predicates import PredicateResult,require_all
def test_all():require_all((PredicateResult("a",True,"x"),),("a",))
def test_missing():
 with pytest.raises(ValueError):require_all((),("a",))
