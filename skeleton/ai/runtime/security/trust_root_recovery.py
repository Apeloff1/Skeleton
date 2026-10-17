"""Non-owning compatibility facade for skeleton.security.trust_root_recovery.

The canonical trust-root recovery owner remains skeleton/security. This AI-tree
surface deliberately owns no keys, verifiers, or revocation state.
"""

from __future__ import annotations

import skeleton.security.trust_root_recovery as _impl
from skeleton.security.trust_root_recovery import *

__all__ = tuple(
    getattr(
        _impl, "__all__", tuple(name for name in dir(_impl) if not name.startswith("_"))
    )
)


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
