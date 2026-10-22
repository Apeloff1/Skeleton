"""Compatibility module for historical runtime-learning imports.

All operational-learning equations, schemas, policy validation and deterministic
optimizer behavior now live in the domain contracts package, so infrastructure
persistence no longer depends upward on an application-layer module.

Identity is preserved: existing imports in other app packages, tests, and
operator adapters resolve to the same canonical module object.
"""
from __future__ import annotations

import sys as _sys
from skeleton.contracts import runtime_learning as _runtime_learning

_sys.modules[__name__] = _runtime_learning
