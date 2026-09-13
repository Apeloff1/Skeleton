import pytest
from skeleton.frontier.gameforge_budget import Budget

def test_budget_never_overcommits():
 b=Budget(3); assert b.reserve(2); assert not b.reserve(2); b.release(1); assert b.reserve(2)

def test_budget_rejects_invalid_release():
 b=Budget(1)
 with pytest.raises(ValueError): b.release()
