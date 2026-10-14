"""End-to-end receipt binding native transformer to canonical local inference

Plane: e2e_inference_receipt
PR: https://github.com/Apeloff1/Skeleton/pull/3483
Branch: ai/native-runtime-e2e-current-head-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3483.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3483"
KIND = "e2e-inference"


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
class Stage:
    stage_id: str
    name: str
    digest: str
    latency_ns: int

    @classmethod
    def create(cls, name: str, digest: str, latency_ns: int):
        _id(name, "name")
        _id(digest, "digest")
        _u(latency_ns, "latency_ns")
        payload = {"name": name, "digest": digest, "latency_ns": latency_ns}
        return cls(_h("stage-sha256:", payload), name, digest, latency_ns)


@dataclass(frozen=True)
class E2EReceipt:
    receipt_id: str
    stage_ids: tuple
    total_ns: int
    root: str


def close(stages: Sequence[Stage]) -> E2EReceipt:
    required = ("encode", "prefill", "decode", "verify", "emit")
    by = {}
    for stage in stages:
        if stage.name not in required:
            raise ValueError("unknown e2e stage")
        if stage.name in by:
            raise PermissionError("duplicate e2e stage")
        by[stage.name] = stage
    if set(by) != set(required):
        raise PermissionError("e2e receipt is incomplete")
    ordered = tuple(by[name] for name in required)
    total = sum(s.latency_ns for s in ordered)
    ids = tuple(s.stage_id for s in ordered)
    root = _h("e2e-root:", {"stage_ids": ids, "total_ns": total})
    return E2EReceipt(_h("e2e-sha256:", {"root": root}), ids, total, root)


def exit_card(receipt: E2EReceipt) -> dict:
    return card(True, receipt_id=receipt.receipt_id, total_ns=receipt.total_ns, root=receipt.root)
