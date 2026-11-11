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
    """Bound traversal and text before the JSON encoder allocates output.

    A post-encoding byte limit alone is insufficient: a direct caller can
    supply a huge string, a deep/cyclic container or a giant integer and force
    substantial allocation before the final length check. The budget counts
    a lower bound on encoded string bytes; the final check remains exact.
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
            # ensure_ascii=True cannot encode a code point in fewer bytes
            # than its one-code-point contribution to len(str).
            remaining -= len(item)
        elif kind is dict:
            if len(item) > maximum:
                raise LaptopGateHold("evidence exceeds finite structure ceiling")
            for key, child in item.items():
                # Do not invoke arbitrary key conversion or comparison.
                if type(key) is not str:
                    raise LaptopGateHold("invalid canonical evidence")
                remaining -= len(key)
                pending.append((child, depth + 1))
        elif kind is list or kind is tuple:
            if len(item) > maximum:
                raise LaptopGateHold("evidence exceeds finite structure ceiling")
            pending.extend((child, depth + 1) for child in item)
        elif kind is int:
            # Prevent decimal conversion of unbounded Python integers.
            if item.bit_length() > maximum * 4:
                raise LaptopGateHold("evidence exceeds finite size ceiling")
        elif kind is bool or kind is float or item is None:
            pass  # The JSON encoder still rejects NaN and infinity.
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
        if not isinstance(self.stages, tuple) or len(self.stages) != 8:
            raise LaptopGateHold("domain must evaluate all eight safeguards")
        if len({x.stage for x in self.stages}) != len(self.stages):
            raise LaptopGateHold("duplicate safeguard result")
        if any(not isinstance(x, StageVerdict) for x in self.stages):
            raise LaptopGateHold("untyped safeguard result")

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
