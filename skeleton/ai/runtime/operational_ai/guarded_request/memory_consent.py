"""Per-principal, explicit-consent source admission; no implicit model memories."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import strict_integer
from .errors import deny
from .identities import Scope, require_id
from .model_pins import require_sha256

MAX_RETENTION_MS = 30 * 24 * 60 * 60 * 1000
CATEGORIES = frozenset({"episodic", "semantic", "document"})


@dataclass(frozen=True, slots=True)
class MemoryConsent:
    scope: Scope
    consent_id: str
    source_sha256: str
    category: str
    approved_by_caller: bool
    issued_ms: int
    expires_ms: int

    def __post_init__(self) -> None:
        if type(self.scope) is not Scope:
            deny("memory-owner")
        require_id(self.consent_id, "consent")
        require_sha256(self.source_sha256)
        if type(self.category) is not str or self.category not in CATEGORIES:
            deny("memory-category")
        if type(self.approved_by_caller) is not bool or not self.approved_by_caller:
            deny("memory-no-consent")
        strict_integer(self.issued_ms, minimum=0, maximum=2**63 - 1, field="issued")
        strict_integer(self.expires_ms, minimum=0, maximum=2**63 - 1, field="expires")
        if not 0 < self.expires_ms - self.issued_ms <= MAX_RETENTION_MS:
            deny("memory-retention")

    def authorize(
        self,
        *,
        scope: Scope,
        source_sha256: str,
        now_ms: int,
        caller_approved: bool,
    ) -> None:
        self.scope.require_same(scope)
        require_sha256(source_sha256)
        strict_integer(now_ms, minimum=0, maximum=2**63 - 1, field="clock")
        if caller_approved is not True:
            deny("memory-no-consent")
        if self.source_sha256 != source_sha256:
            deny("memory-source")
        if not self.issued_ms <= now_ms < self.expires_ms:
            deny("memory-expired")
