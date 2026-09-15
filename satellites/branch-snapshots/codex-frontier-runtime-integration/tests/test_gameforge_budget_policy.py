from skeleton.frontier.gameforge_budget_policy import BudgetPolicy

def test_policy_permits_within_capacity():
    p = BudgetPolicy(3)
    assert p.permits(2)
    assert not p.permits(3)

def test_policy_rejects_invalid_values():
    try:
        BudgetPolicy(0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid policy accepted")
