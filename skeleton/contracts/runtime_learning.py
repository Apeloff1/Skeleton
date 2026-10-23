"""Compatibility export of the canonical deterministic runtime-learning domain.

The implementation remains single-owner in runtime_learning_core; legacy and
new import paths refer to the same module object and policy authority.
"""
from __future__ import annotations

import sys as _sys
from skeleton.contracts import runtime_learning_core as _core

_sys.modules[__name__] = _core
