"""Compatibility shim; canonical implementation lives in skeleton.persistence.core.cards.

FROZEN (issue #4122): ``skeleton.persist`` is frozen in place. New code must
import only ``skeleton.persistence``; migration into the canonical package is
tracked in issue #4122. Docstring-only notice: no behaviour change, no warning.

Deprecated: use skeleton.persistence.core.cards.
"""
from skeleton.persistence.core.cards import *  # noqa: F401,F403
__deprecated__ = "skeleton.persistence"  # issue #4122: docstring-only deprecation, no warning
