"""Tenant, request, session and model identity validation.

Identities never come from model text. No normalization that could silently
merge distinct principals is applied to an admitted identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .canonical import ContractViolation, require_digest

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$", re.ASCII)


def require_id(value: object, *, field: str = "identifier") -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ContractViolation(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class Actor:
    tenant: str
    user: str
    model_digest: str
    tokenizer_digest: str

    def __post_init__(self) -> None:
        require_id(self.tenant, field="tenant")
        require_id(self.user, field="user")
        require_digest(self.model_digest, field="model digest")
        require_digest(self.tokenizer_digest, field="tokenizer digest")

    @property
    def scope(self) -> tuple[str, str, str, str]:
        return self.tenant, self.user, self.model_digest, self.tokenizer_digest

    def to_record(self) -> dict[str, str]:
        return {"tenant": self.tenant, "user": self.user,
                "model_digest": self.model_digest,
                "tokenizer_digest": self.tokenizer_digest}


@dataclass(frozen=True, slots=True)
class OperationId:
    session: str
    request: str
    revision: int

    def __post_init__(self) -> None:
        require_id(self.session, field="session")
        require_id(self.request, field="request")
        if type(self.revision) is not int or not 0 <= self.revision <= 1_000_000:
            raise ContractViolation("invalid revision")

    @property
    def key(self) -> str:
        return f"{self.session}/{self.request}"
