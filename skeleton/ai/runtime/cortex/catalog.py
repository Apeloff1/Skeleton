"""Non-owning compatibility facade for the canonical implementation at skeleton.cortex.catalog.

This AI-tree surface deliberately owns no provider credentials, secret storage,
or network policy. Attribute fallback preserves compatibility until explicit cutover.
"""
from __future__ import annotations

import skeleton.cortex.catalog as _impl
from skeleton.cortex.catalog import *  # noqa: F401,F403

__all__ = tuple(getattr(_impl, "__all__", tuple(name for name in dir(_impl) if not name.startswith("_"))))


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
