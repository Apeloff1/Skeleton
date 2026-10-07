"""Context provenance chain through native inference

Plane: context_provenance_chain
PR: https://github.com/Apeloff1/Skeleton/pull/3484
Branch: integration/native-context-provenance-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3484.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3484"
KIND = "context-provenance"


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

N_CAP = 8


@dataclass(frozen=True)
class PointerClause:
    clause_id: str
    url: str
    era: str
    ordinal: int

    @classmethod
    def create(cls, url: str, era: str, ordinal: int):
        _id(url, "url")
        _id(era, "era")
        _u(ordinal, "ordinal")
        if " " in url or not (url.startswith("https://") or url.startswith("github.com/") or url.startswith("arxiv.org/")):
            raise ValueError("url must be a pointer")
        payload = {"url": url, "era": era, "ordinal": ordinal}
        return cls(_h("clause-sha256:", payload), url, era, ordinal)


@dataclass(frozen=True)
class ProvenanceRoot:
    root_id: str
    clause_ids: tuple
    n: int


def bind(clauses: Sequence[PointerClause]) -> ProvenanceRoot:
    if not clauses:
        raise ValueError("provenance requires at least one pointer")
    if len(clauses) > N_CAP:
        raise PermissionError("pointer N-cap exceeded")
    ordered = tuple(sorted(clauses, key=lambda c: (c.ordinal, c.url)))
    ordinals = [c.ordinal for c in ordered]
    if ordinals != sorted(set(ordinals)):
        raise PermissionError("ordinal collision or gap")
    ids = tuple(c.clause_id for c in ordered)
    return ProvenanceRoot(_h("prov-sha256:", {"clause_ids": ids}), ids, len(ids))


def exit_card(root: ProvenanceRoot) -> dict:
    return card(True, root_id=root.root_id, n=root.n, stored_prose=0)
