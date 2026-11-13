"""Monotone bounded resource admission with explicit spending receipts."""
from dataclasses import dataclass, field
from .errors import ContractError, BudgetError

@dataclass
class Budget:
    maximum: dict[str, int]
    spent: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.maximum or any((not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool) or (v < 0) for k, v in self.maximum.items())):
            raise ContractError('invalid resource maximum')
        if any((k not in self.maximum or not isinstance(v, int) or v < 0 or (v > self.maximum[k]) for k, v in self.spent.items())):
            raise ContractError('invalid existing spend')

    def charge(self, costs: dict[str, int]) -> dict[str, int]:
        if not isinstance(costs, dict) or any((k not in self.maximum or not isinstance(v, int) or isinstance(v, bool) or (v < 0) for k, v in costs.items())):
            raise ContractError('invalid resource charge')
        if any((self.spent.get(k, 0) + v > self.maximum[k] for k, v in costs.items())):
            raise BudgetError('resource ceiling exceeded')
        for k, v in costs.items():
            self.spent[k] = self.spent.get(k, 0) + v
        return dict(self.spent)

    def remaining(self, key: str) -> int:
        if key not in self.maximum:
            raise ContractError('unknown resource')
        return self.maximum[key] - self.spent.get(key, 0)
