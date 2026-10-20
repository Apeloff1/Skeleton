"""Compatibility import for canonical deterministic learning codec.

The pure implementation lives in skeleton.contracts so lower-layer persistence
can validate data without importing the application intelligence plane.
Existing application callers retain exact module identity and patch semantics.
"""
from __future__ import annotations

import sys as _sys
from skeleton.contracts import runtime_learning_core as _core

_sys.modules[__name__] = _core
