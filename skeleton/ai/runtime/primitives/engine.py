"""Compose ring + merkle + ops + activations. Import stays network-free."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from skeleton.primitives import activations, ops
from skeleton.primitives.cards import assert_card, primitive_card
from skeleton.primitives.kinds import catalog_card, kind_count, require_kind
from skeleton.primitives.law import KIND_COUNT, RING_CAP
from skeleton.primitives.merkle import merkle_card, root_of
from skeleton.primitives.ring import Ring
from skeleton.primitives.viscera_bridge import viscera_card


class PrimitiveEngine:
    def __init__(self) -> None:
        self.ring = Ring()
        self.cards: list[dict[str, Any]] = []

    def _emit(self, card: dict[str, Any]) -> dict[str, Any]:
        assert_card(card)
        require_kind(str(card["kind"]))
        self.cards.append(card)
        return card

    def push(self, token: str) -> dict[str, Any]:
        self.ring.push(token)
        return self._emit(self.ring.card())

    def apply_op(self, name: str, **kwargs: Any) -> dict[str, Any]:
        fn: Callable[..., dict[str, Any]] = getattr(ops, name)
        card = fn(**kwargs)
        return self._emit(card)

    def apply_activation(self, name: str, xs: Iterable[float]) -> dict[str, Any]:
        return self._emit(activations.activation_card(name, list(xs)))

    def compact(self) -> dict[str, Any]:
        return self._emit(ops.compact(self.ring))

    def bridge(self, *, G: float, root: str | None = None) -> dict[str, Any]:
        if root is None:
            root = root_of(self.ring.items())
        card = viscera_card(G=G, law="viscera_card thin", root=root)
        return self._emit(card)

    def snapshot(self) -> dict[str, Any]:
        leaves = self.ring.items()
        return {
            "kind_count": kind_count(),
            "ring": leaves,
            "cap": RING_CAP,
            "root": root_of(leaves),
            "n_cards": len(self.cards),
            "stored_prose": 0,
        }

    def health(self) -> dict[str, Any]:
        ok = kind_count() == KIND_COUNT and len(self.ring) <= RING_CAP
        catalog = catalog_card()
        merkle = merkle_card(self.ring.items())
        return primitive_card(
            kind="ring",
            hit=1 if ok else 0,
            law="engine health",
            extra={
                "catalog_hit": catalog["hit"],
                "merkle_root": merkle.get("root"),
                "ring_size": len(self.ring),
            },
        )
