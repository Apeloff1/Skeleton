"""Seven structural ops. Each returns a card. No stored sentence."""

from __future__ import annotations

from typing import Sequence

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.kinds import require_kind
from skeleton.primitives.merkle import merkle_card, root_of
from skeleton.primitives.ring import Ring


def bond(left: str, right: str) -> dict:
    require_kind("bond")
    token = left + "+" + right
    return primitive_card(kind="bond", hit=1, law="bond", extra={"token": token})


def quench(token: str, heat: float) -> dict:
    require_kind("quench")
    cooled = 1 if heat >= 0.90 else 0
    return primitive_card(
        kind="quench",
        hit=cooled,
        law="quench",
        extra={"token": token, "heat": heat, "cooled": cooled},
    )


def witness(leaves: Sequence[str]) -> dict:
    require_kind("witness")
    card = merkle_card(leaves)
    card["kind"] = "witness"
    card["law"] = "witness"
    return card


def gossip(local_root: str, peer_root: str) -> dict:
    require_kind("gossip")
    same = int(local_root == peer_root)
    return primitive_card(
        kind="gossip",
        hit=same,
        law="gossip",
        extra={"local": local_root, "peer": peer_root},
    )


def fork(token: str, n: int = 2) -> dict:
    require_kind("fork")
    if n < 1:
        n = 1
    branches = [token + "#" + str(i) for i in range(n)]
    return primitive_card(kind="fork", hit=1, law="fork", extra={"branches": branches})


def house(vertices: Sequence[str]) -> dict:
    require_kind("house")
    return primitive_card(
        kind="house",
        hit=1 if vertices else 0,
        law="house pointers",
        extra={"n": len(vertices)},
    )


def compact(ring: Ring) -> dict:
    require_kind("compact")
    leaves = ring.items()
    root = root_of(leaves) if leaves else root_of([])
    return primitive_card(
        kind="compact",
        hit=1,
        law="compact",
        extra={"root": root, "n": len(leaves)},
    )
