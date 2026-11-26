"""Local AI package. Facade exports load on first use.

Importing a tool module such as ``pdf_ops`` does not boot the Jeeves facade.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from types import ModuleType
from typing import Any

__all__ = ["LocalAIComplete", "get_complete", "SEAMS"]

_LAZY = {
    "LocalAIComplete": ("skeleton.local_ai.local_ai_complete", "LocalAIComplete"),
    "get_complete": ("skeleton.local_ai.local_ai_complete", "get_complete"),
    "SEAMS": ("skeleton.local_ai.local_ai_index", "SEAMS"),
}

# Literal loaders keep facade resolution statically auditable (no runtime-built
# module names); every module named in _LAZY must have exactly one loader here.
_LOADERS: dict[str, Callable[[], ModuleType]] = {
    "skeleton.local_ai.local_ai_complete": lambda: import_module("skeleton.local_ai.local_ai_complete"),
    "skeleton.local_ai.local_ai_index": lambda: import_module("skeleton.local_ai.local_ai_index"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(_LOADERS[module_name](), attr)
    globals()[name] = value
    return value
