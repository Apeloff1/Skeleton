"""Reconcile governed crawler-to-generation spine

Plane: spine_reconcile
PR: https://github.com/Apeloff1/Skeleton/pull/3477
Branch: automation/crawler-retrieval-context-bridge-v2-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3477.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3477"
KIND = "spine-reconcile"


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _h(prefix: str, payload: object) -> str:
    return prefix + sha256(_canon(payload).encode("utf-8")).hexdigest()


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    if "\n" in value or len(value) > 240:
        raise ValueError(f"{name} must be a pointer clause")
    return value.strip()


def _u(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def card(hit: bool, **extra: object) -> dict:
    body = {
        "kind": KIND,
        "hit": bool(hit),
        "law": LAW,
        "citation": CITATION,
        "stored_prose": 0,
    }
    body.update(extra)
    if body["stored_prose"] != 0:
        raise PermissionError("stored prose is forbidden")
    return body

@dataclass(frozen=True)
class SpineNode:
    node_id: str
    plane: str
    digest: str

    @classmethod
    def create(cls, plane: str, digest: str):
        if plane not in {"crawl", "retrieve", "context", "generate"}:
            raise ValueError("unknown spine plane")
        _id(digest, "digest")
        payload = {"plane": plane, "digest": digest}
        return cls(_h("node-sha256:", payload), plane, digest)


@dataclass(frozen=True)
class Spine:
    spine_id: str
    node_ids: tuple
    root: str


def reconcile(nodes: Sequence[SpineNode]) -> Spine:
    order = ("crawl", "retrieve", "context", "generate")
    by = {}
    for node in nodes:
        if node.plane in by:
            raise PermissionError("duplicate spine plane")
        by[node.plane] = node
    if set(by) != set(order):
        raise PermissionError("spine is incomplete")
    ids = tuple(by[name].node_id for name in order)
    root = _h("spine-root:", {"node_ids": ids})
    return Spine(_h("spine-sha256:", {"root": root}), ids, root)


def exit_card(spine: Spine) -> dict:
    return card(True, spine_id=spine.spine_id, root=spine.root, planes=4)
