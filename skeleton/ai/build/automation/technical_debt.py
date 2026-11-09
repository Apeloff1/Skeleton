"""Compatibility surface for VOL-115 technical debt ledger.

Canonical ownership lives in :mod:`skeleton.contracts.technical_debt`.
This module intentionally contains no independent debt-retirement policy.
"""

from skeleton.contracts.technical_debt import *  # noqa: F401,F403
from skeleton.contracts.technical_debt import __all__ as __all__
