"""Local AI package. Facade exports load on first use.

Importing a tool module such as ``pdf_ops`` does not boot the Jeeves facade.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["LocalAIComplete", "get_complete", "SEAMS"]

_LAZY = {
    "LocalAIComplete": ("skeleton.local_ai.local_ai_complete", "LocalAIComplete"),
    "get_complete": ("skeleton.local_ai.local_ai_complete", "get_complete"),
    "SEAMS": ("skeleton.local_ai.local_ai_index", "SEAMS"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
