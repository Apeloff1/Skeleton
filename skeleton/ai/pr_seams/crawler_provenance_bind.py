"""Bind crawler provenance into retrieval and context

Plane: crawler_provenance_bind
PR: https://github.com/Apeloff1/Skeleton/pull/3476
Branch: automation/crawler-retrieval-context-bridge-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3476.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3476"
KIND = "crawler-provenance"


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
class CrawlPointer:
    pointer_id: str
    url: str
    fetched_ns: int
    digest: str

    @classmethod
    def create(cls, url: str, fetched_ns: int, digest: str):
        _id(url, "url")
        _u(fetched_ns, "fetched_ns")
        _id(digest, "digest")
        if not url.startswith("https://"):
            raise ValueError("crawl pointer must be https")
        payload = {"url": url, "fetched_ns": fetched_ns, "digest": digest}
        return cls(_h("crawl-sha256:", payload), url, fetched_ns, digest)


@dataclass(frozen=True)
class RetrievalBind:
    bind_id: str
    pointer_id: str
    context_id: str
    root: str


def bind(pointer: CrawlPointer, context_id: str) -> RetrievalBind:
    _id(context_id, "context_id")
    root = _h("bind-root:", {"pointer_id": pointer.pointer_id, "context_id": context_id, "digest": pointer.digest})
    return RetrievalBind(_h("rbind-sha256:", {"root": root}), pointer.pointer_id, context_id, root)


def exit_card(bound: RetrievalBind) -> dict:
    return card(True, bind_id=bound.bind_id, pointer_id=bound.pointer_id, context_id=bound.context_id, root=bound.root)
