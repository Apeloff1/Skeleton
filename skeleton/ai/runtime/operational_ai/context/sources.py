"""Admission of bounded, provenance-bearing evidence; data never becomes policy."""
from __future__ import annotations
from dataclasses import dataclass
from ..authority.canonical import ContractViolation, require_small_text, require_digest, sha256
from ..authority.identity import require_id

TRUST_LEVELS = frozenset({"user-supplied", "local-document", "tool-result", "model-generated"})
MAX_EVIDENCE_BYTES = 64_000


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    owner_tenant: str
    owner_user: str
    origin: str
    body: str
    digest: str
    trust: str
    rights: str
    revision: int = 1

    def __post_init__(self) -> None:
        for name in ("source_id", "owner_tenant", "owner_user"):
            require_id(getattr(self,name),field=name)
        require_small_text(self.origin,field="evidence origin",maximum=512)
        require_small_text(self.body,field="evidence body",maximum=MAX_EVIDENCE_BYTES)
        require_small_text(self.rights,field="rights",maximum=512)
        require_digest(self.digest,field="evidence digest")
        if self.trust not in TRUST_LEVELS:
            raise ContractViolation("unsupported evidence trust label")
        if sha256(self.body.encode("utf-8"))!=self.digest:
            raise ContractViolation("evidence body hash mismatch")
        if type(self.revision) is not int or not 1<=self.revision<=1_000_000:
            raise ContractViolation("invalid evidence revision")

    @classmethod
    def create(cls,source_id:str,tenant:str,user:str,origin:str,body:str,
               *,rights:str,trust:str="user-supplied",revision:int=1) -> "Source":
        return cls(source_id,tenant,user,origin,body,sha256(body.encode("utf-8")),
                   trust,rights,revision)

    def to_record(self) -> dict[str,object]:
        return {"id":self.source_id,"tenant":self.owner_tenant,"user":self.owner_user,
                "origin":self.origin,"sha256":self.digest,"trust":self.trust,
                "rights":self.rights,"revision":self.revision}
