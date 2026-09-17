"""Catalog economy as cards. Bag ops reversible. Weights sum to 1. No coin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


EPS = 1e-9
MAX_ITEMS = 64
MAX_QTY = 10_000


class HarborError(ValueError):
    """Harbor contract violation."""


def _token(name: str) -> str:
    text = str(name or "").strip()
    if not text or len(text) > 64:
        raise HarborError("item name invalid")
    if text.lower() in {"coin", "token", "currency-network", "on-chain"}:
        raise HarborError("coin/network currency is forbidden")
    return text


@dataclass
class Harbor:
    """Lineage-weighted bag. Weight sum must equal 1."""

    weights: dict[str, float] = field(default_factory=dict)
    bag: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.weights = {_token(k): float(v) for k, v in (self.weights or {}).items()}
        self.bag = {_token(k): int(v) for k, v in (self.bag or {}).items()}
        if self.weights:
            total = sum(self.weights.values())
            if abs(total - 1.0) > EPS:
                raise HarborError("lineage weights must sum to 1")
        if len(self.bag) > MAX_ITEMS or len(self.weights) > MAX_ITEMS:
            raise HarborError("harbor exceeds item cap")
        for qty in self.bag.values():
            if qty < 0 or qty > MAX_QTY:
                raise HarborError("bag quantity out of range")

    def put(self, item: str, qty: int = 1) -> "Harbor":
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise HarborError("qty must be a positive integer")
        name = _token(item)
        nxt = dict(self.bag)
        nxt[name] = nxt.get(name, 0) + qty
        if nxt[name] > MAX_QTY:
            raise HarborError("bag quantity out of range")
        self.bag = nxt
        return self

    def take(self, item: str, qty: int = 1) -> "Harbor":
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise HarborError("qty must be a positive integer")
        name = _token(item)
        have = self.bag.get(name, 0)
        if have < qty:
            raise HarborError("bag underflow")
        nxt = dict(self.bag)
        left = have - qty
        if left:
            nxt[name] = left
        else:
            nxt.pop(name, None)
        self.bag = nxt
        return self

    def snapshot(self) -> dict[str, Any]:
        return {
            "kind": "economy",
            "bag": dict(sorted(self.bag.items())),
            "harbor": True,
            "weights": dict(sorted(self.weights.items())),
            "sum": round(sum(self.weights.values()), 9) if self.weights else 0.0,
            "stored_prose": 0,
        }


def harbor_from_mapping(raw: Mapping[str, Any] | None) -> Harbor:
    data = dict(raw or {})
    return Harbor(weights=dict(data.get("weights") or {}), bag=dict(data.get("bag") or {}))
