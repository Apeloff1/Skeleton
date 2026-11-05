"""No silent quota escalation: authority attenuation and spend must both pass."""
from ..contracts.limits import Budget
from .authority import Grant

def admit(grant: Grant, scope: str, logical_time: int, budget: Budget, cost: dict[str, int]) -> dict:
    grant.check(scope, logical_time)
    return budget.charge(cost)
