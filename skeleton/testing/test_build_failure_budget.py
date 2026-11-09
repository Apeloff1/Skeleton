import pytest
from skeleton.automation.build_failure_budget import FailureBudget
def test_category_budget():
 b=FailureBudget({})
 for _ in range(4):b=b.record("validation")
 with pytest.raises(ValueError):b.record("validation")
def test_unknown_is_tight():
 b=FailureBudget({}).record("unknown")
 with pytest.raises(ValueError):b.record("unknown")
