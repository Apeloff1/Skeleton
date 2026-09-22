"""Pointed spaces. S is the unit sphere object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pointed:
    name: str
    base: str
    points: frozenset[str]

    def __post_init__(self) -> None:
        if self.base not in self.points:
            raise ValueError("base")


def sphere() -> Pointed:
    return Pointed("S", "*", frozenset(("*", "gen")))


def wedge(a: Pointed, b: Pointed) -> Pointed:
    pts = set()
    for p in a.points:
        pts.add(a.name + ":" + p if p != a.base else "*")
    for p in b.points:
        pts.add(b.name + ":" + p if p != b.base else "*")
    pts.add("*")
    return Pointed("vee(%s,%s)" % (a.name, b.name), "*", frozenset(pts))
