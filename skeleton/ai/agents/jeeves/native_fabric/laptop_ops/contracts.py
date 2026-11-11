"""Typed non-authoritative laptop admission evidence and bounded results."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Mapping

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class LaptopGateHold(ValueError):
    """Malformed operator evidence or missing mandatory proof."""


def name(value: object) -> str:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise LaptopGateHold("invalid bounded evidence identifier")
    return value


def sha(value: object) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise LaptopGateHold("noncanonical sha256 digest")
    return value


def integer(value: object, *, ceiling: int = 10**13) -> int:
    if type(value) is not int or not 0 <= value <= ceiling:
        raise LaptopGateHold("finite nonnegative integer required")
    return value


def _preflight_canonical(value: object, maximum: int) -> None:
    """Bound aggregate encoded evidence before the JSON encoder allocates.

    Account for *all* scalar values and container punctuation, not only
    strings. A large list of builtin integers, floats or empty strings can
    otherwise allocate far beyond the output ceiling before the post-encode
    check. Every charge is a lower bound on the eventual ASCII JSON size.
    """
    if type(maximum) is not int or maximum < 1:
        raise LaptopGateHold("invalid finite canonical ceiling")

    pending: list[tuple[object, int]] = [(value, 0)]
    remaining = maximum
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > maximum or depth > 64:
            raise LaptopGateHold("evidence exceeds finite structure ceiling")

        kind = type(item)
        if kind is str:
            # Two JSON quotes plus at least one byte per code point.
            remaining -= len(item) + 2
        elif kind is dict:
            count = len(item)
            if count > maximum:
                raise LaptopGateHold("evidence exceeds finite structure ceiling")
            remaining -= 2 + max(0, count - 1)  # braces and commas
            for key, child in item.items():
                if type(key) is not str:
                    raise LaptopGateHold("invalid canonical evidence")
                remaining -= len(key) + 3  # key quotes and colon
                pending.append((child, depth + 1))
        elif kind is list or kind is tuple:
            count = len(item)
            if count > maximum:
                raise LaptopGateHold("evidence exceeds finite structure ceiling")
            remaining -= 2 + max(0, count - 1)  # brackets and commas
            pending.extend((child, depth + 1) for child in item)
        elif kind is int:
            bits = item.bit_length()
            if bits > maximum * 4:
                raise LaptopGateHold("evidence exceeds finite size ceiling")
            # 3/10 < log10(2): conservative decimal digit lower bound.
            digits = max(1, ((bits - 1) * 3) // 10 + 1)
            remaining -= digits + (1 if item < 0 else 0)
        elif kind is bool:
            remaining -= 4 if item else 5
        elif kind is float:
            # Builtin float repr is bounded and requires no JSON allocation.
            remaining -= len(repr(item))
        elif item is None:
            remaining -= 4
        else:
            raise LaptopGateHold("invalid canonical evidence")

        if remaining < 0:
            raise LaptopGateHold("evidence exceeds finite size ceiling")


def canonical(value: object, *, maximum: int = 65536) -> bytes:
    _preflight_canonical(value, maximum)
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, OverflowError,
            RecursionError) as exc:
        raise LaptopGateHold("invalid canonical evidence") from exc
    if len(data) > maximum:
        raise LaptopGateHold("evidence exceeds finite size ceiling")
    return data


def fingerprint(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class StageVerdict:
    stage: str
    accepted: bool
    code: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        name(self.stage)
        name(self.code)
        if type(self.accepted) is not bool:
            raise LaptopGateHold("stage verdict requires strict boolean")
        sha(self.evidence_sha256)

    def to_record(self) -> dict[str, object]:
        return {"stage": self.stage, "accepted": self.accepted,
                "code": self.code, "evidence_sha256": self.evidence_sha256}


@dataclass(frozen=True, slots=True)
class DomainVerdict:
    domain: str
    stages: tuple[StageVerdict, ...]
    evidence_sha256: str

    def __post_init__(self) -> None:
        name(self.domain)
        sha(self.evidence_sha256)
        if type(self.stages) is not tuple or len(self.stages) != 8:
            raise LaptopGateHold("domain must evaluate all eight safeguards")
        # Reject foreign objects and tuple subclasses *before* invoking
        # caller-defined __iter__, __getattribute__, __hash__, or equality.
        if any(type(item) is not StageVerdict for item in self.stages):
            raise LaptopGateHold("untyped safeguard result")
        if len({item.stage for item in self.stages}) != len(self.stages):
            raise LaptopGateHold("duplicate safeguard result")

    @property
    def accepted(self) -> bool:
        return all(item.accepted for item in self.stages)

    def to_record(self) -> dict[str, object]:
        return {"schema": "jeeves.laptop_ops.domain.v1",
                "domain": self.domain, "accepted": self.accepted,
                "stages": [item.to_record() for item in self.stages],
                "evidence_sha256": self.evidence_sha256,
                "operator_claims_are_not_authority": True,
                "native_inference_witnessed": False,
                "physical_device_qualified": False,
                "release_certified": False}
