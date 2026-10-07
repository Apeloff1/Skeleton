"""Structural invariants that must hold for any valid spine chain."""

from __future__ import annotations

from typing import Callable

from skeleton.spine.articulation import all_rom_ok
from skeleton.spine.chain import SpineChain, assert_chain_integrity
from skeleton.spine.digest import assert_digest_format, chain_digest
from skeleton.spine.law import SEGMENT_N, STORED_PROSE, VERTEBRA_N
from skeleton.spine.taxonomy import validate_catalog
from skeleton.spine.topology import has_cycle, is_connected, is_path_graph, validate_topology


class InvariantError(AssertionError):
    pass


def inv_counts(chain: SpineChain) -> None:
    if len(chain.vertebrae) != VERTEBRA_N:
        raise InvariantError("vertebra_n")
    if len(chain.segments) != SEGMENT_N:
        raise InvariantError("segment_n")


def inv_integrity(chain: SpineChain) -> None:
    assert_chain_integrity(chain)


def inv_catalog() -> None:
    validate_catalog()


def inv_topology() -> None:
    validate_topology()
    if has_cycle() or not is_connected() or not is_path_graph():
        raise InvariantError("topology")


def inv_rom(chain: SpineChain) -> None:
    if not all_rom_ok(chain.segments):
        raise InvariantError("rom")


def inv_digest(chain: SpineChain) -> None:
    d = chain_digest(chain)
    assert_digest_format(d)


def inv_stored_prose_zero(card: dict) -> None:
    if card.get("stored_prose", 1) != STORED_PROSE:
        raise InvariantError("stored_prose")


def inv_labels_unique(chain: SpineChain) -> None:
    labels = chain.labels()
    if len(labels) != len(set(labels)):
        raise InvariantError("duplicate-labels")


def inv_ordinal_order(chain: SpineChain) -> None:
    from skeleton.spine.taxonomy import ordinal_of

    ords = [ordinal_of(lb) for lb in chain.labels()]
    if ords != list(range(VERTEBRA_N)):
        raise InvariantError("ordinal-order")


INVARIANTS: list[tuple[str, Callable[..., None]]] = [
    ("counts", inv_counts),
    ("integrity", inv_integrity),
    ("labels", inv_labels_unique),
    ("ordinals", inv_ordinal_order),
    ("rom", inv_rom),
    ("digest", inv_digest),
]


def check_all(chain: SpineChain) -> list[str]:
    """Return list of failed invariant names."""
    failed: list[str] = []
    inv_catalog()
    inv_topology()
    for name, fn in INVARIANTS:
        try:
            fn(chain)
        except Exception:
            failed.append(name)
    return failed


def assert_all(chain: SpineChain) -> None:
    failed = check_all(chain)
    if failed:
        raise InvariantError(",".join(failed))
