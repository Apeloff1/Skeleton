"""Legacy import alias for the canonical provider boundary.

Provider classes, registry state, credentials and execution remain owned by
``skeleton.provider_runtime``. This alias preserves their object identities.
"""

from skeleton import provider_runtime as _canonical
from skeleton.provider_runtime import *  # Compatibility re-export.

__all__ = _canonical.__all__


def __getattr__(name: str):
    return getattr(_canonical, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_canonical)))
