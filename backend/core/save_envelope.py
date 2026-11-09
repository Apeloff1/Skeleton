"""Versioned save envelope with deterministic integrity verification.

Mined from Newmove2 save-system semantics and redesigned for server/native/web
storage adapters. Payloads are canonicalized, checksummed, migrated explicitly,
and rejected on corruption rather than silently trusting damaged state.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable


class SaveIntegrityError(ValueError):
    pass


Migration = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SaveEnvelope:
    version: int
    payload: dict[str, Any]
    checksum: str


class SaveCodec:
    def __init__(self, current_version: int, migrations: dict[int, Migration] | None = None) -> None:
        if current_version <= 0:
            raise ValueError("current_version must be positive")
        self.current_version = current_version
        self.migrations = dict(migrations or {})

    @staticmethod
    def _canonical(version: int, payload: dict[str, Any]) -> bytes:
        return json.dumps(
            {"version": version, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def checksum(self, version: int, payload: dict[str, Any]) -> str:
        return sha256(self._canonical(version, payload)).hexdigest()

    def encode(self, payload: dict[str, Any]) -> str:
        checksum = self.checksum(self.current_version, payload)
        return json.dumps(
            {"version": self.current_version, "payload": payload, "checksum": checksum},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def decode(self, raw: str) -> SaveEnvelope:
        try:
            data = json.loads(raw)
            version = int(data["version"])
            payload = dict(data["payload"])
            checksum = str(data["checksum"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SaveIntegrityError("malformed save envelope") from exc
        if version <= 0 or version > self.current_version:
            raise SaveIntegrityError("unsupported save version")
        expected = self.checksum(version, payload)
        if checksum != expected:
            raise SaveIntegrityError("save checksum mismatch")
        while version < self.current_version:
            migration = self.migrations.get(version)
            if migration is None:
                raise SaveIntegrityError(f"missing migration from version {version}")
            payload = dict(migration(dict(payload)))
            version += 1
        return SaveEnvelope(
            version=self.current_version,
            payload=payload,
            checksum=self.checksum(self.current_version, payload),
        )

    def reencode(self, raw: str) -> str:
        envelope = self.decode(raw)
        return self.encode(envelope.payload)
