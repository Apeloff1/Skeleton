"""Organism + organismer — 10× Genos path over galaxy and social pointers.

Heavy symbols are lazy-loaded so policy_enforcement (and other leaf modules)
can import without pulling cortex/intelligence and creating cycles.
"""
from __future__ import annotations

__all__ = ["Organismer", "live_organismer", "reset_organismer", "product_card"]


def __getattr__(name: str):
    if name in {"Organismer", "live_organismer", "reset_organismer"}:
        from skeleton.organism import organismer as _organismer
        return getattr(_organismer, name)
    if name == "product_card":
        from skeleton.organism.product import product_card
        return product_card
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
