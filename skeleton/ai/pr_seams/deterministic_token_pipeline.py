"""Deterministic text-to-token pipeline

Plane: deterministic_token_pipeline
PR: https://github.com/Apeloff1/Skeleton/pull/3474
Branch: automation/llm-token-pipeline-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3474.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3474"
KIND = "token-pipeline"


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
class Token:
    token_id: int
    piece: str
    start: int
    end: int


@dataclass(frozen=True)
class PipelineReceipt:
    receipt_id: str
    text_hash: str
    token_ids: tuple
    n: int


def tokenize(text: str) -> tuple:
    if not isinstance(text, str):
        raise ValueError("text must be str")
    if len(text) > 8192:
        raise ValueError("text exceeds pipeline bound")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in text):
        raise ValueError("control characters are rejected")
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            piece = text[i:j]
        elif ch.isalnum() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            piece = text[i:j]
        else:
            j = i + 1
            piece = text[i:j]
        token_id = int(sha256(piece.encode("utf-8")).hexdigest()[:8], 16)
        out.append(Token(token_id, piece, i, j))
        i = j
    return tuple(out)


def receipt(text: str) -> PipelineReceipt:
    tokens = tokenize(text)
    ids = tuple(t.token_id for t in tokens)
    text_hash = sha256(text.encode("utf-8")).hexdigest()
    payload = {"text_hash": text_hash, "token_ids": ids}
    return PipelineReceipt(_h("tok-sha256:", payload), text_hash, ids, len(ids))


def exit_card(bound: PipelineReceipt) -> dict:
    return card(True, receipt_id=bound.receipt_id, n=bound.n, text_hash=bound.text_hash)
