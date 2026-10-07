from __future__ import annotations

from types import SimpleNamespace

from skeleton.galaxy.atoms import Atom
from skeleton.galaxy.graph import edges_of, reconstruct


def _atom(atom_id: str) -> Atom:
    return Atom(
        id=atom_id,
        kind="capture",
        tier="T0_FLASH",
        topic=f"topic-{atom_id}",
        dialect="memory graph",
        brain="memory",
        color="blue",
        tokens=("memory", "graph"),
    )


def _mesh(atoms: list[Atom]) -> SimpleNamespace:
    shelf = {atom.id: atom for atom in atoms}
    return SimpleNamespace(brains={}, wiki=SimpleNamespace(shelf=shelf))


def test_edges_of_is_stable_across_atom_insertion_order() -> None:
    atoms = [_atom("c"), _atom("a"), _atom("b")]

    forward = edges_of(atoms)
    reverse = edges_of(list(reversed(atoms)))

    assert forward == reverse
    assert forward == [
        ("a", "b", 1.0),
        ("a", "c", 1.0),
        ("b", "c", 1.0),
    ]


def test_reconstruct_is_stable_across_atom_insertion_order() -> None:
    atoms = [_atom("d"), _atom("c"), _atom("b"), _atom("a")]

    forward = reconstruct(_mesh(atoms), "memory graph", k=3)
    reverse = reconstruct(_mesh(list(reversed(atoms))), "memory graph", k=3)

    assert forward == reverse
    assert [node["id"] for node in forward["nodes"]] == ["a", "b", "c"]
    assert forward["edges"] == [{"a": "a", "b": "c", "w": 1.0}]
