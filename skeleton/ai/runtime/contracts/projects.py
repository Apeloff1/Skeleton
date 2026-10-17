"""Projects contract re-export.

The canonical schema is ``skeleton.contracts.projects``. This module stays
importable so runtime callers do not keep a second Projects shape.
"""

from __future__ import annotations

from skeleton.contracts import projects as _canonical

__all__ = list(_canonical.__all__)
globals().update({name: getattr(_canonical, name) for name in __all__})
