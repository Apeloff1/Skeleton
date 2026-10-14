"""Compatibility surface for VOL-118 governed roadmap control.

Canonical ownership lives in :mod:`skeleton.contracts.roadmap_control`.
This module intentionally contains no independent planning, scope, or replan
authority.
"""

from skeleton.contracts.roadmap_control import *  # noqa: F401,F403
from skeleton.contracts.roadmap_control import __all__ as __all__
