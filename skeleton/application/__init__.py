"""Compatibility namespace for the canonical application runtime.

New code should import from :mod:`skeleton.app.runtime`.
"""
from skeleton.app.runtime import *  # noqa: F401,F403
from skeleton.app.runtime import __all__ as __all__
