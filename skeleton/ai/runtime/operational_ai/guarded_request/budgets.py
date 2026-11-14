"""Finite non-escalating budgets with atomic usage charges."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from .contracts import strict_integer
from .errors import deny


@dataclass(frozen=True, slots=True)
class Quota:
    context_tokens: int = 8192
    output_tokens: int = 512
    input_bytes: int = 16384
    output_bytes: int = 131072
    tool_calls: int = 0
    parallel_requests: int = 1

    def __post_init__(self) -> None:
        bounds = {
            "context_tokens": (64, 262144),
            "output_tokens": (1, 32768),
            "input_bytes": (1, 1048576),
            "output_bytes": (1, 1048576),
            "tool_calls": (0, 256),
            "parallel_requests": (1, 256),
        }
        for field, (lo, hi) in bounds.items():
            strict_integer(getattr(self, field), minimum=lo, maximum=hi, field=field)
        if self.output_tokens >= self.context_tokens:
            deny("context-reserve")

    def attenuate(self, **constraints: int) -> "Quota":
        fields = self.__dataclass_fields__
        if not constraints or any(k not in fields for k in constraints):
            deny("quota-keys")
        values = {field: getattr(self, field) for field in fields}
        for field, amount in constraints.items():
            strict_integer(amount, minimum=0, maximum=values[field], field=field)
            values[field] = amount
        return Quota(**values)


class QuotaUsage:
    """Charges are all-or-nothing, including under concurrent callers."""

    def __init__(self, limit: Quota):
        self.limit = limit
        self._used = {"input_bytes": 0, "output_bytes": 0, "tool_calls": 0}
        self._lock = Lock()

    @property
    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._used)

    def charge(self, **requested: int) -> dict[str, int]:
        with self._lock:
            candidate = dict(self._used)
            for key, amount in requested.items():
                if key not in candidate:
                    deny("quota-charge-key")
                strict_integer(amount, minimum=0, maximum=getattr(self.limit, key), field=key)
                candidate[key] += amount
                if candidate[key] > getattr(self.limit, key):
                    deny("quota-exhausted")
            self._used = candidate
            return dict(candidate)
