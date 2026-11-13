"""Bind a live production supervisor to exact model and principal identities."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import exact,identifier,identity_hash,refuse

@dataclass(frozen=True,slots=True)
class ActiveModel:
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str

    def __post_init__(self):
        identifier(self.tenant,"tenant")
        identifier(self.subject,"subject")
        identity_hash(self.model_sha256);identity_hash(self.tokenizer_sha256)

    @classmethod
    def from_supervisor(cls,worker):
        try:
            identity=worker.spine.identity
            backend=worker.spine.backend
            result=cls(identity.tenant,identity.subject,
                       identity.model_sha256,identity.tokenizer_sha256)
            if (backend.model_digest!=result.model_sha256 or
                backend.tokenizer_digest!=result.tokenizer_sha256):
                refuse("active backend differs from principal binding")
            return result
        except AttributeError as exc:
            raise ValueError("production supervisor must own a real execution spine") from exc

    def to_record(self):
        return {"tenant":self.tenant,"subject":self.subject,
                "model_sha256":self.model_sha256,
                "tokenizer_sha256":self.tokenizer_sha256}
