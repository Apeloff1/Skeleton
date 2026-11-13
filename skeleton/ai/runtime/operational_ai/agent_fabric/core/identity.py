"""Tenant/user/model/tokenizer binding for autonomous operations."""
from dataclasses import dataclass
from .canonical import identifier,hex_digest,digest
@dataclass(frozen=True,slots=True)
class Identity:
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    def __post_init__(self):
        identifier(self.tenant,'tenant');identifier(self.subject,'subject')
        hex_digest(self.model_sha256,'model');hex_digest(self.tokenizer_sha256,'tokenizer')
    def record(self):return dict(tenant=self.tenant,subject=self.subject,model_sha256=self.model_sha256,tokenizer_sha256=self.tokenizer_sha256)
    def key(self):return digest({'schema':'agent.identity.v1',**self.record()})
    @classmethod
    def from_spine(cls,identity):
        return cls(identity.tenant,identity.subject,identity.model_sha256,identity.tokenizer_sha256)
