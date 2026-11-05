"""B081-B090: security lane evidence contracts (B091-B100 platform lane owned elsewhere).

Deterministic, fail-closed evidence contracts. Each ``bNNN_*`` module turns the
batch's success criterion from ``skeleton/repo_intelligence/game_creation_batches.json``
into code with a stable canonical-JSON digest. Existing enforcement (e.g.
:mod:`skeleton.sandbox`, :mod:`skeleton.security`) is complemented, not replaced.
"""
from ._core import ContractError, Verdict, canonical, digest

BATCHES = tuple(f"B{n:03d}" for n in range(81, 91))
__all__ = ["BATCHES", "ContractError", "Verdict", "canonical", "digest"]
