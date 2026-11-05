"""Non-escalating, immutable operation limits and finite resource charges."""
from __future__ import annotations

from dataclasses import dataclass, replace
import time
from .canonical import ContractViolation, require_number


@dataclass(frozen=True, slots=True)
class Limits:
    input_bytes: int = 32_768
    output_bytes: int = 32_768
    context_tokens: int = 8_192
    output_tokens: int = 512
    tool_calls: int = 0
    retrieval_hits: int = 8
    memory_bytes: int = 2_097_152
    deadline_ms: int = 60_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            require_number(getattr(self, name), field=name, maximum=2**31 - 1)
        if not self.input_bytes or not self.output_bytes or not self.context_tokens:
            raise ContractViolation("zero capacity is not operational")
        if not self.output_tokens or self.output_tokens >= self.context_tokens:
            raise ContractViolation("output reservation must fit context window")
        if not self.deadline_ms or self.deadline_ms > 86_400_000:
            raise ContractViolation("deadline outside bounded interval")

    def attenuate(self, **tightened: int) -> "Limits":
        fields = self.__dataclass_fields__
        if any(key not in fields or type(value) is not int or value < 0 or
               value > getattr(self, key) for key, value in tightened.items()):
            raise ContractViolation("budget attenuation cannot escalate limits")
        return replace(self, **tightened)

    def to_record(self) -> dict[str, int]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class BudgetLedger:
    """Charge before a side effect; never let a failed operation refund effects."""

    def __init__(self, limits: Limits):
        if not isinstance(limits, Limits):
            raise ContractViolation("bounded limits required")
        self.limits = limits
        self.spent = {key: 0 for key in limits.__dataclass_fields__ if key != "deadline_ms"}
        self.started_ns = time.monotonic_ns()

    def deadline(self) -> None:
        if (time.monotonic_ns() - self.started_ns) // 1_000_000 >= self.limits.deadline_ms:
            raise ContractViolation("operation deadline exceeded")

    def charge(self, **costs: int) -> dict[str, int]:
        self.deadline()
        pending = dict(self.spent)
        for name, charge in costs.items():
            if name not in pending or type(charge) is not int or charge < 0:
                raise ContractViolation("invalid resource charge")
            pending[name] += charge
            if pending[name] > getattr(self.limits, name):
                raise ContractViolation(f"resource limit exceeded: {name}")
        self.spent = pending
        return dict(self.spent)

    def remaining(self, field: str) -> int:
        if field not in self.spent:
            raise ContractViolation("unknown remaining resource")
        return getattr(self.limits, field) - self.spent[field]
