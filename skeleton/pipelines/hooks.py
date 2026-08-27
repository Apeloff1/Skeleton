"""Pipeline hooks — pre/post stage extensions with shared context.

Validating isn't the only lifecycle extension; hooks attach callables
to specific moments (before-stage, after-stage, on-error) without
rewiring the runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

from skeleton.kernel.errors import PipelineError


class HookError(PipelineError):
    code = "PPL.HOOK"


class HookPoint(str, Enum):
    BEFORE_STAGE = "BEFORE_STAGE"
    AFTER_STAGE = "AFTER_STAGE"
    ON_ERROR = "ON_ERROR"


@dataclass(frozen=True)
class Hook:
    name: str
    point: HookPoint
    run: Callable[[Any], None]


class HookRegistry:
    """Attach and run hooks by point; the runner consults this."""

    def __init__(self) -> None:
        self._hooks: Dict[HookPoint, List[Hook]] = {}

    def attach(self, hook: Hook) -> None:
        self._hooks.setdefault(hook.point, []).append(hook)

    def run(self, point: HookPoint, payload: Any) -> None:
        for hook in self._hooks.get(point, []):
            try:
                hook.run(payload)
            except Exception as exc:
                raise HookError(
                    "hook failed",
                    context={"hook": hook.name, "point": point.value},
                ) from exc
