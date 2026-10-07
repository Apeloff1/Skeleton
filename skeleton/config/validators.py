"""Per-key validators for config snapshots.

kernel ConfigStore.propose() accepts values; validators run named
predicates over dotted keys and reject bad values before activation.
The bridge (skeleton.config.snapshots) invokes this on propose.

- :class:`KeyValidator` — dotted key + predicate + message
- :class:`ValidatorRegistry` — validate(values, actor) → problems
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from skeleton.kernel.errors import ConfigurationError


@dataclass(frozen=True)
class KeyValidator:
    key: str  # dotted e.g. "rag.top_k"
    predicate: Callable[[Any], bool]
    message: str


class ValidatorRegistry:
    """Named validators run on a flat settings map."""

    def __init__(self) -> None:
        self._validators = list()  # ordered

    def register(self, validator: KeyValidator) -> None:
        self._validators.append(validator)

    def validate(self, values: Dict[str, Any]) -> Tuple[str, ...]:
        problems: List[str] = []
        for validator in self._validators:
            if validator.key not in values:
                continue
            if not validator.predicate(values[validator.key]):
                problems.append(f"{validator.key}: {validator.message}")
        return tuple(problems)

    def check_or_raise(self, values: Dict[str, Any], *, actor: str = "unknown") -> None:
        problems = self.validate(values)
        if problems:
            raise ConfigurationError(
                "config validators failed",
                context={"actor": actor, "problems": list(problems)},
            )
