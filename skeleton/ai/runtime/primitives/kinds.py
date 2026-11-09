"""Frozen 12-kind catalog. Kind count must stay 12."""

from __future__ import annotations

from typing import Iterable

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.errors import KindError
from skeleton.primitives.law import KIND_COUNT, KINDS


def kind_set() -> frozenset[str]:
    return frozenset(KINDS)


def kind_count() -> int:
    return len(KINDS)


def require_kind(name: str) -> str:
    if name not in KINDS:
        raise KindError(name)
    return name


def reject_extra(names: Iterable[str]) -> None:
    extra = [n for n in names if n not in KINDS]
    if extra:
        raise KindError("extra:" + ",".join(sorted(set(extra))))
    seen = list(names)
    if len(set(seen)) > KIND_COUNT:
        raise KindError("grew")


def catalog_card() -> dict:
    return primitive_card(
        kind="ring",
        hit=1 if kind_count() == KIND_COUNT else 0,
        law="kinds==12",
        extra={"kinds": list(KINDS), "kind_count": kind_count()},
    )
