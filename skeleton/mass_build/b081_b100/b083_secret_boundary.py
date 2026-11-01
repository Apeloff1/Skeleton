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
MAX_ARTIFACTS = 256
MAX_ARTIFACT_CHARS = 1_000_000
MAX_CREDENTIALS = 256
MAX_AUDIT_EVENTS = 10_000


def scan(text: str) -> list[str]:
    require(type(text) is str and len(text) <= MAX_ARTIFACT_CHARS,
            "secret scan input exceeds bound")
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
        require(len(self.name) <= 128, "credential name exceeds bound")
        require(type(self.issued_at) is int and type(self.expires_at) is int
                and 0 <= self.issued_at < self.expires_at,
                "credential must have bounded integer lifetime")
        require(type(self.scopes) is tuple and len(self.scopes) <= 32
                and all(type(scope) is str and 1 <= len(scope) <= 128 for scope in self.scopes),
                "credential scopes exceed bound")


class CredentialLedger:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, str]] = []

    def use(self, cred: Credential, scope: str, now: int) -> bool:
        require(type(now) is int and now >= 0, "audit time must be a nonnegative integer")
        require(type(scope) is str and 1 <= len(scope) <= 128, "audit scope exceeds bound")
        require(len(self.events) < MAX_AUDIT_EVENTS, "credential audit log exceeds bound")
        ok = scope in cred.scopes and cred.issued_at <= now < cred.expires_at
        self.events.append((now, cred.name, f"{scope}:{'ok' if ok else 'deny'}"))
        return ok


def evaluate(artifacts: dict[str, str], creds: list[Credential]):
    require(type(artifacts) is dict and len(artifacts) <= MAX_ARTIFACTS,
            "artifact collection exceeds bound")
    require(type(creds) is list and len(creds) <= MAX_CREDENTIALS
            and all(isinstance(c, Credential) for c in creds),
            "credential collection exceeds bound")
    require(all(type(path) is str and 1 <= len(path) <= 512 for path in artifacts),
            "artifact path exceeds bound")
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
