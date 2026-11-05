"""B092: engine-neutral IR for scenes/mechanics/assets with validation and stable digests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._helpers import ContractError, digest, require, require_str

IR_VERSION = 1
NODE_TYPES = frozenset(
    {
        "Node",
        "Node2D",
        "Node3D",
        "Sprite",
        "Camera",
        "Light",
        "Body",
        "Area",
        "Audio",
        "UI",
    }
)


@dataclass
class IRProject:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    mechanics: dict[str, dict[str, Any]] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)  # id -> sha256

    def add_node(
        self, nid: str, ntype: str, parent: str | None = None, **props: Any
    ) -> None:
        require_str(nid, "node id")
        require(nid not in self.nodes, f"duplicate node {nid}")
        require(ntype in NODE_TYPES, f"unknown node type {ntype}")
        require(parent is None or parent in self.nodes, f"unknown parent {parent}")
        self.nodes[nid] = {
            "id": nid,
            "type": ntype,
            "parent": parent,
            "props": dict(props),
        }

    def add_mechanic(self, mid: str, kind: str, params: dict[str, Any]) -> None:
        require(mid not in self.mechanics, f"duplicate mechanic {mid}")
        self.mechanics[mid] = {
            "id": mid,
            "kind": require_str(kind, "kind"),
            "params": dict(params),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ir_version": IR_VERSION,
            "nodes": self.nodes,
            "mechanics": self.mechanics,
            "assets": self.assets,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IRProject":
        if d.get("ir_version") != IR_VERSION:
            raise ContractError(f"unsupported ir_version {d.get('ir_version')}")
        p = cls()
        pending = dict(d["nodes"])
        while pending:  # parents first, deterministic order
            ready = sorted(
                k
                for k, n in pending.items()
                if n["parent"] is None or n["parent"] in p.nodes
            )
            require(bool(ready), "cycle or dangling parent in IR")
            for k in ready:
                n = pending.pop(k)
                p.add_node(k, n["type"], n["parent"], **n["props"])
        for k in sorted(d["mechanics"]):
            m = d["mechanics"][k]
            p.add_mechanic(k, m["kind"], m["params"])
        p.assets = dict(d["assets"])
        return p
