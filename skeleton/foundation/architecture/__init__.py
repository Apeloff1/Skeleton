"""Canonical architecture registry and historical architecture rounds.

The stable base model remains at :mod:`skeleton.architecture`. The canonical
index and numbered historical rounds live here so the package root stays
navigable while legacy imports remain supported through compatibility shims.
"""

__all__ = ["index", "rounds"]
