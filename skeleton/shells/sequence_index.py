"""Shared contracts for bounded secondary sequence-index backfill.

Sequence indexes are acceleration metadata for durable hash-linked evidence
chains.  These records describe a bounded backfill batch without granting the
index any authority over the underlying journal or receipt chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, runtime_checkable


def _digest(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be a 64-character digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be hexadecimal"
        ) from exc
    return value.lower()


@dataclass(frozen=True)
class SequenceIndexBackfillBatch:
    requested_end_sequence: int
    requested_end_root: str
    covered_start_sequence: int | None
    covered_end_sequence: int | None
    indexed: int
    already_indexed: int
    next_sequence: int
    next_root: str
    complete_to_genesis: bool

    def __post_init__(self) -> None:
        for name in (
            "requested_end_sequence",
            "indexed",
            "already_indexed",
            "next_sequence",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be a non-negative integer"
                )
        for name in (
            "covered_start_sequence",
            "covered_end_sequence",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive when present"
                )
        object.__setattr__(
            self,
            "requested_end_root",
            _digest(
                "requested_end_root",
                self.requested_end_root,
            ),
        )
        object.__setattr__(
            self,
            "next_root",
            _digest(
                "next_root",
                self.next_root,
            ),
        )
        if not isinstance(
            self.complete_to_genesis,
            bool,
        ):
            raise ValueError(
                "complete_to_genesis must be bool"
            )

        covered = self.indexed + self.already_indexed
        if self.requested_end_sequence == 0:
            if (
                self.covered_start_sequence is not None
                or self.covered_end_sequence is not None
                or covered != 0
                or self.next_sequence != 0
                or not self.complete_to_genesis
            ):
                raise ValueError(
                    "empty backfill batch is inconsistent"
                )
            return

        if (
            self.covered_start_sequence is None
            or self.covered_end_sequence is None
        ):
            raise ValueError(
                "non-empty backfill batch requires covered sequence bounds"
            )
        if (
            self.covered_end_sequence
            != self.requested_end_sequence
        ):
            raise ValueError(
                "backfill covered end must equal requested end"
            )
        if (
            self.covered_start_sequence
            > self.covered_end_sequence
        ):
            raise ValueError(
                "backfill covered range is reversed"
            )
        expected = (
            self.covered_end_sequence
            - self.covered_start_sequence
            + 1
        )
        if covered != expected:
            raise ValueError(
                "backfill counters do not match covered range"
            )
        if (
            self.next_sequence
            != self.covered_start_sequence - 1
        ):
            raise ValueError(
                "backfill next sequence is not contiguous"
            )
        if self.complete_to_genesis != (
            self.next_sequence == 0
        ):
            raise ValueError(
                "backfill completion disagrees with next sequence"
            )

    @property
    def covered_items(self) -> int:
        return self.indexed + self.already_indexed

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "requested_end_sequence": (
                self.requested_end_sequence
            ),
            "requested_end_root": self.requested_end_root,
            "covered_start_sequence": (
                self.covered_start_sequence
            ),
            "covered_end_sequence": (
                self.covered_end_sequence
            ),
            "indexed": self.indexed,
            "already_indexed": self.already_indexed,
            "covered_items": self.covered_items,
            "next_sequence": self.next_sequence,
            "next_root": self.next_root,
            "complete_to_genesis": (
                self.complete_to_genesis
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@runtime_checkable
class SequenceIndexBackfillableChain(Protocol):
    def head(self): ...

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool: ...

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence: int | None = None,
        end_root: str = "",
        max_items: int = 1024,
    ) -> SequenceIndexBackfillBatch: ...
