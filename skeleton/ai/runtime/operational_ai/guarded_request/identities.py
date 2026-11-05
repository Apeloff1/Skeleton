"""Canonical tenant/user/session/request scope boundaries."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .errors import deny

_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)


def require_id(value: Any, field: str = "identity") -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        deny(field + "-invalid")
    return value


@dataclass(frozen=True, slots=True)
class Scope:
    tenant: str
    user: str
    session: str
    model_digest: str

    def __post_init__(self) -> None:
        from .model_pins import require_sha256
        for field in ("tenant", "user", "session"):
            require_id(getattr(self, field), field)
        require_sha256(self.model_digest)

    @property
    def key(self) -> str:
        return "/".join((self.tenant, self.user, self.session, self.model_digest))

    def require_same(self, other: "Scope") -> None:
        if type(other) is not Scope or self != other:
            deny("scope-mismatch")
