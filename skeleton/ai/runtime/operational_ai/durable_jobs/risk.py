"""Independent execution-risk policy. A native model cannot issue grants."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import deny
from .spec import JobIdentity,require_id

_SAFE=frozenset({"inspect","list","history","verify","cancel_own"})
_PRIVILEGED=frozenset({"manual_resume","archive","purge","export_audit"})
_FORBIDDEN=frozenset({"shell","network","run_generated_code","write_unscoped"})


@dataclass(frozen=True, slots=True)
class OperatorGrant:
    owner: JobIdentity
    allowed: frozenset[str]
    expires_ms: int

    def __post_init__(self):
        from .canonical import require_int
        if type(self.owner) is not JobIdentity or type(self.allowed) is not frozenset:
            deny("grant-owner")
        if not self.allowed.issubset(_SAFE | _PRIVILEGED):
            deny("grant-unsupported")
        require_int(self.expires_ms,0,2**63-1,"grant-expires")

    def check(self,owner:JobIdentity,action:str,now_ms:int,
              *,verified_human_operator:bool=False)->None:
        from .canonical import require_int
        require_id(action,"operation")
        require_int(now_ms,0,2**63-1,"clock")
        if owner!=self.owner:
            deny("grant-principal")
        if now_ms>=self.expires_ms:
            deny("grant-expired")
        if action not in self.allowed:
            deny("grant-missing")
        if action in _PRIVILEGED and verified_human_operator is not True:
            deny("grant-needs-operator")
