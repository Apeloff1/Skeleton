"""Typed canonical identifiers for VOL-298.

Identifiers contain only immutable kind and opaque value. Display labels,
tenant names, roles, permissions, or other mutable authority data are never
encoded into identifier syntax.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata
import uuid


_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_VALUE = re.compile(r"^[a-z0-9][a-z0-9._~-]{0,126}$")


class IdentifierKind(str, Enum):
    OPERATION = "operation"
    ARTIFACT = "artifact"
    AGENT = "agent"
    MODEL = "model"
    EVIDENCE = "evidence"
    RECEIPT = "receipt"


@dataclass(frozen=True, order=True)
class Identifier:
    kind: IdentifierKind
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _VALUE.fullmatch(self.value):
            raise ValueError("identifier value is not canonical")

    def __str__(self) -> str:
        return IdentifierCodec.encode(self)


class IdentifierCodec:
    VERSION = "id1"

    @classmethod
    def encode(cls, identifier: Identifier) -> str:
        return f"{cls.VERSION}:{identifier.kind.value}:{identifier.value}"

    @classmethod
    def parse(cls, raw: str) -> Identifier:
        if not isinstance(raw, str) or not raw or raw != unicodedata.normalize("NFKC", raw):
            raise ValueError("identifier must be non-empty NFKC text")
        if raw != raw.strip() or raw.lower() != raw:
            raise ValueError("identifier must use exact lowercase canonical form")
        parts = raw.split(":")
        if len(parts) != 3 or parts[0] != cls.VERSION:
            raise ValueError("identifier must use id1:<kind>:<value>")
        kind_text, value = parts[1], parts[2]
        if not _TOKEN.fullmatch(kind_text):
            raise ValueError("identifier kind token is not canonical")
        try:
            kind = IdentifierKind(kind_text)
        except ValueError as exc:
            raise ValueError("unknown identifier kind") from exc
        identifier = Identifier(kind, value)
        if cls.encode(identifier) != raw:
            raise ValueError("identifier is not in canonical form")
        return identifier

    @staticmethod
    def new(kind: IdentifierKind) -> Identifier:
        return Identifier(kind, uuid.uuid4().hex)


def deterministic_identifier(kind: IdentifierKind, namespace: uuid.UUID, immutable_name: str) -> Identifier:
    if not isinstance(immutable_name, str) or not immutable_name:
        raise ValueError("immutable name is required")
    normalized = unicodedata.normalize("NFKC", immutable_name)
    if normalized != immutable_name:
        raise ValueError("immutable name must already be NFKC normalized")
    return Identifier(kind, uuid.uuid5(namespace, immutable_name).hex)
