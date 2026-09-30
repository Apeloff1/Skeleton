"""Governed AI compatibility facade for the canonical provider contract.

Provider-neutral contract ownership remains at `skeleton.providers.contract`
until an explicit owner cutover. This destination intentionally re-exports the
same class and enum objects so source and AI namespace imports cannot diverge
at runtime.
"""

from skeleton.providers.contract import *  # noqa: F401,F403
from skeleton.providers.contract import __all__ as __all__
