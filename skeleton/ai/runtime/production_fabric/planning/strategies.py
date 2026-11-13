"""Bounded goal/subgoal selection; requires explicit deterministic feasibility."""
from ..contracts.graph import topological
from ..contracts.errors import ContractError

def plan(goals: dict[str, list[str]], target: str, *, max_steps: int=1000) -> list[str]:
    order = topological(goals)
    if target not in goals or len(order) > max_steps:
        raise ContractError('plan unavailable or unbounded')
    needed = {target}
    pending = [target]
    while pending:
        for dep in goals[pending.pop()]:
            if dep not in needed:
                needed.add(dep)
                pending.append(dep)
    return [step for step in order if step in needed]
