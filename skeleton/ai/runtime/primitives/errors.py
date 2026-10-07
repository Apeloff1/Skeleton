"""Fail-closed errors for the primitives plane."""

from __future__ import annotations


class PrimitivesError(Exception):
    """Base error. Import of skeleton.primitives never raises this."""


class KindError(PrimitivesError):
    """Unknown or extra kind."""


class RingCapError(PrimitivesError):
    """Ring would exceed cap 24."""


class MerkleError(PrimitivesError):
    """Merkle proof or leaf mismatch."""


class CardError(PrimitivesError):
    """Card missing required keys or stored_prose != 0."""


class VisceraImportError(PrimitivesError):
    """Primitives imported viscera. Forbidden."""
