"""mint / link / gossip / walk / tick. Walk path cap 8."""

from __future__ import annotations

from skeleton.hive.cards import hive_card
from skeleton.hive.law import HISTORY_KEEP, WALK_CAP
from skeleton.hive.merkle import digest, fold, merkle_pair


class Hive:
    def __init__(self) -> None:
        self.roots: list[str] = []
        self.links: list[tuple[str, str, str]] = []
        self.ticks: int = 0
        self.graph: dict[str, list[str]] = {}

    def mint(self, payload: str) -> dict:
        root = digest("mint:" + payload)
        self.roots.append(root)
        self.graph.setdefault(root, [])
        return hive_card(kind="mint", hit=1, law="mint root", extra={"root": root})

    def link(self, parent: str, child_payload: str) -> dict:
        child = digest("link:" + parent + ":" + child_payload)
        bound = merkle_pair(parent, child)
        self.roots.append(bound)
        self.links.append((parent, child, bound))
        self.graph.setdefault(parent, []).append(child)
        self.graph.setdefault(child, [])
        return hive_card(
            kind="link",
            hit=1,
            law="link roots",
            extra={"parent": parent, "child": child, "root": bound},
        )

    def card_root(self, root: str) -> dict:
        return hive_card(kind="root", hit=1, law="card{root}", extra={"root": root})

    def gossip(self, peer_root: str | None = None) -> dict:
        if peer_root is None:
            peer_root = self.roots[-1] if self.roots else digest("self")
        self.roots.append(peer_root)
        hist = self.roots[-HISTORY_KEEP:]
        return hive_card(
            kind="gossip",
            hit=1,
            law="gossip merkle",
            extra={
                "root": peer_root,
                "peer_roots": hist[-2:],
                "consensus": fold(hist),
                "n_history": len(self.roots),
                "last": hist,
            },
        )

    def walk(self, start: str) -> dict:
        path = [start]
        seen = {start}
        cur = start
        while len(path) < WALK_CAP:
            nxts = [n for n in self.graph.get(cur, []) if n not in seen]
            if not nxts:
                break
            cur = nxts[0]
            seen.add(cur)
            path.append(cur)
        return hive_card(
            kind="walk",
            hit=1 if len(path) <= WALK_CAP else 0,
            law="walk cap 8",
            extra={"path": path, "n": len(path)},
        )

    def tick(self) -> dict:
        self.ticks += 1
        g = self.gossip()
        return hive_card(
            kind="tick",
            hit=1,
            law="tick then gossip",
            extra={"ticks": self.ticks, "root": g.get("root"), "consensus": g.get("consensus")},
        )
