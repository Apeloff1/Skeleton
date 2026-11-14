"""Explicit caller authority only; no model-authored shell, network or writes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from .errors import deny
from .identities import Scope, require_id
from .contracts import strict_integer

_ALLOWED_READ = frozenset({"hash_text", "count_text", "read_bounded_text", "inspect_receipt", "search_local"})


@dataclass(frozen=True, slots=True)
class ReadGrant:
    scope: Scope
    tools: FrozenSet[str]
    expires_mono_ns: int

    def __post_init__(self) -> None:
        if type(self.scope) is not Scope or type(self.tools) is not frozenset:
            deny("grant-type")
        if not self.tools.issubset(_ALLOWED_READ):
            deny("grant-unsupported-effect")
        for name in self.tools:
            require_id(name, "tool")
        strict_integer(self.expires_mono_ns, minimum=1, maximum=2**63 - 1, field="expiration")

    def check(self, *, scope: Scope, tool: str, now_ns: int, mutating: bool = False) -> None:
        self.scope.require_same(scope)
        require_id(tool, "tool")
        strict_integer(now_ns, minimum=0, maximum=2**63 - 1, field="clock")
        if mutating or tool not in self.tools or tool not in _ALLOWED_READ:
            deny("grant-effect")
        if now_ns >= self.expires_mono_ns:
            deny("grant-expired")

    def attenuate(self, selected: FrozenSet[str], *, expires_mono_ns: int) -> "ReadGrant":
        if type(selected) is not frozenset or not selected.issubset(self.tools):
            deny("grant-escalation")
        if expires_mono_ns > self.expires_mono_ns:
            deny("grant-escalation")
        return ReadGrant(self.scope, selected, expires_mono_ns)
