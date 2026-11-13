"""B083: secrets never enter artifacts/logs; credentials short-lived, scoped, audited."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ._core import ContractError, require, require_str, verdict

PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?:password|secret|token)\s*[:=]\s*\S{8,}"),
)
MAX_TTL_S = 3600


def scan(text: str) -> list[str]:
    hits = []
    for i, p in enumerate(PATTERNS):
        if p.search(text):
            hits.append(f"pattern{i}")
    return hits


@dataclass(frozen=True)
class Credential:
    name: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        require_str(self.name, "name")
        require(self.expires_at > self.issued_at, "credential must expire after issue")


class CredentialLedger:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, str]] = []

    def use(self, cred: Credential, scope: str, now: int) -> bool:
        ok = scope in cred.scopes and cred.issued_at <= now < cred.expires_at
        self.events.append((now, cred.name, f"{scope}:{'ok' if ok else 'deny'}"))
        return ok


def evaluate(artifacts: dict[str, str], creds: list[Credential]):
    findings = []
    for path in sorted(artifacts):
        for h in scan(artifacts[path]):
            findings.append(f"secret:{path}:{h}")
    for c in creds:
        if c.expires_at - c.issued_at > MAX_TTL_S:
            findings.append(f"long_lived:{c.name}")
        if "*" in c.scopes:
            findings.append(f"wildcard_scope:{c.name}")
    return verdict("B083", findings, artifacts=len(artifacts), credentials=len(creds))
