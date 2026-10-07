"""Crawler Python newline corruption witness

Plane: python_newline_witness
PR: https://github.com/Apeloff1/Skeleton/pull/3481
Branch: automation/crawler-python-syntax-repair-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3481.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3481"
KIND = "syntax-witness"


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
class SourceWitness:
    witness_id: str
    digest: str
    line_count: int
    corrupt: bool
    reason: str


def witness(source: str) -> SourceWitness:
    if not isinstance(source, str):
        raise ValueError("source must be text")
    if len(source) > 200_000:
        raise ValueError("source exceeds witness bound")
    digest = sha256(source.encode("utf-8")).hexdigest()
    reasons = []
    if "\r" in source and "\n" not in source:
        reasons.append("cr-only")
    if "\x00" in source:
        reasons.append("nul")
    if source and not source.endswith("\n"):
        reasons.append("missing-final-newline")
    collapsed = source.replace("\n", "")
    if source and "def " in collapsed and "\n" not in source:
        reasons.append("collapsed-def")
    line_count = source.count("\n")
    corrupt = bool(reasons)
    reason = ",".join(reasons) if reasons else "clean"
    payload = {"digest": digest, "line_count": line_count, "corrupt": corrupt, "reason": reason}
    return SourceWitness(_h("nl-sha256:", payload), digest, line_count, corrupt, reason)


def repair_newlines(source: str) -> str:
    found = witness(source)
    if not found.corrupt:
        return source if source.endswith("\n") else source + "\n"
    text = source.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if text and not text.endswith("\n"):
        text += "\n"
    after = witness(text)
    if after.corrupt and after.reason not in {"clean"}:
        # residual corruption other than the forms we can close is rejected
        if "collapsed-def" in after.reason or "cr-only" in after.reason or "nul" in after.reason:
            raise PermissionError("newline repair did not close")
    return text


def exit_card(found: SourceWitness) -> dict:
    return card(not found.corrupt, witness_id=found.witness_id, corrupt=found.corrupt, reason=found.reason, digest=found.digest)
