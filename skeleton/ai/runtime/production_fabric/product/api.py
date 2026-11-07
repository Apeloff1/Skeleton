"""Compatibility entrypoint for the canonical offline production dispatcher.

Keep a single LocalAPI class identity across the public import path, CLI and
canonical dispatcher. A second class definition can silently split monkeypatches,
registration, and authorization instrumentation between otherwise identical APIs.
No network or model-provider authority is granted by this facade.
"""

from __future__ import annotations

from .dispatcher import LocalAPI

__all__ = ["LocalAPI"]
