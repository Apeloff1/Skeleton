"""One live source, model, tokenizer and owner across native Jeeves effects.

The same installed-model witness already used by first-turn acceptance
remains the sole authority for source rights, isolated GGUF health and
capacity-lease custody. This fence does not invoke inference, allocate
SQLite sessions, grant tools or certify a physical device or release.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel


class NativeSourceEpochHold(ValueError):
    """A private native output cannot be attributed to the activated source."""


_SOURCE_FIELDS=(
    "model_sha256", "tokenizer_sha256", "manifest_sha256",
    "archive_sha256", "source_sha",
    "installed_model_bytes", "installed_shard_count",
)


def _identity(worker: object) -> ActiveModel:
    try:
        return ActiveModel.from_supervisor(worker)
    except Exception as exc:
        raise NativeSourceEpochHold(
            "native source/principal no longer available"
        ) from exc


def _source(worker: object, receipt: object) -> tuple[object, ...]:
    try:
        source=require_activated_source(worker,receipt)
        if type(source) is not dict or set(source)!=set(_SOURCE_FIELDS):
            raise NativeSourceEpochHold("incomplete installed source witness")
        result=tuple(source[key] for key in _SOURCE_FIELDS)
        for value in result[:4]:
            if (type(value) is not str or len(value)!=64
                    or any(ch not in "0123456789abcdef" for ch in value)):
                raise NativeSourceEpochHold("invalid native SHA-256 witness")
        origin=result[4]
        if (type(origin) is not str or len(origin) not in (40,64)
                or any(ch not in "0123456789abcdef" for ch in origin)):
            raise NativeSourceEpochHold("invalid installed source revision")
        if (type(result[5]) is not int or result[5]<1
                or type(result[6]) is not int or result[6]<1):
            raise NativeSourceEpochHold("invalid installed source inventory")
        return result
    except Exception as exc:
        raise NativeSourceEpochHold(
            "live installed native source verification held"
        ) from exc


@dataclass(frozen=True,slots=True)
class NativeSourceEpoch:
    """Capture immutable source/owner once; refresh live custody on each use."""

    worker: Any
    installed_receipt: Any
    principal: ActiveModel
    source_fields: tuple[object, ...]

    @classmethod
    def capture(cls,worker: object,installed_receipt: object) -> "NativeSourceEpoch":
        prior=_identity(worker)
        source=_source(worker,installed_receipt)
        if source[:2]!=(prior.model_sha256,prior.tokenizer_sha256):
            raise NativeSourceEpochHold("installed source differs from bound model")
        if _identity(worker)!=prior:
            raise NativeSourceEpochHold("native principal changed during source binding")
        return cls(worker,installed_receipt,prior,source)

    def assert_current(self) -> None:
        if _identity(self.worker)!=self.principal:
            raise NativeSourceEpochHold("native model or owner changed")
        current=_source(self.worker,self.installed_receipt)
        if current!=self.source_fields:
            raise NativeSourceEpochHold("installed GGUF source or capacity changed")
        if _identity(self.worker)!=self.principal:
            raise NativeSourceEpochHold("native principal changed during source inspection")


__all__=["NativeSourceEpoch","NativeSourceEpochHold"]
