"""B083: secrets never enter artifacts/logs; credentials short-lived, scoped, audited."""
from __future__ import annotations

import re
import unicodedata
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
MAX_AUDIT_TIMESTAMP = 1_000_000_000_000


def _safe_diagnostic(value: str) -> bool:
    """Reject controls and invisible format characters in audit identifiers."""
    return type(value) is str and not any(
        unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in value
    )


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
        require(len(self.name) <= 128 and _safe_diagnostic(self.name),
                "credential name exceeds diagnostic bound")
        require(type(self.issued_at) is int and type(self.expires_at) is int
                and 0 <= self.issued_at < self.expires_at <= MAX_AUDIT_TIMESTAMP,
                "credential must have bounded integer lifetime")
        require(type(self.scopes) is tuple and len(self.scopes) <= 32
                and all(type(scope) is str and 1 <= len(scope) <= 128
                        and _safe_diagnostic(scope) for scope in self.scopes),
                "credential scopes exceed bound")


class CredentialLedger:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, str]] = []

    def use(self, cred: Credential, scope: str, now: int) -> bool:
        require(isinstance(cred, Credential), "audit credential must be typed")
        require(type(now) is int and 0 <= now <= MAX_AUDIT_TIMESTAMP,
                "audit time must be a bounded nonnegative integer")
        require(type(scope) is str and 1 <= len(scope) <= 128
                and _safe_diagnostic(scope), "audit scope exceeds bound")
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
    require(all(type(path) is str and 1 <= len(path) <= 512
                and _safe_diagnostic(path) for path in artifacts),
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
