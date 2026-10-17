"""Compatibility namespace for canonical persistence primitives.

New code should import from :mod:`skeleton.persistence.core`.

FROZEN (issue #4122): ``skeleton.persist`` is frozen in place. New code must
import only ``skeleton.persistence``; migration into the canonical package is
tracked in issue #4122. Docstring-only notice: no behaviour change, no warning.
"""
from skeleton.persistence.core import *  # noqa: F401,F403
