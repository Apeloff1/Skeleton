"""Typed source-bound request, identity, timeout and finite work budget."""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any
from .canonical import fingerprint, require_int, require_sha, require_text
from .errors import deny

_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)


def require_id(value: Any, name: str = "id") -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        deny("identity-"+name)
    return value


@dataclass(frozen=True, slots=True)
class JobIdentity:
    tenant: str
    user: str
    session: str
    model_sha256: str
    tokenizer_sha256: str

    def __post_init__(self):
        for key in ("tenant","user","session"):
            require_id(getattr(self,key), key)
        require_sha(self.model_sha256)
        require_sha(self.tokenizer_sha256)

    @property
    def principal(self):
        return self.tenant + ":" + self.user

    def to_record(self):
        return {key:getattr(self,key) for key in
                ("tenant","user","session","model_sha256","tokenizer_sha256")}


@dataclass(frozen=True, slots=True)
class WorkLimits:
    input_bytes: int = 16384
    output_tokens: int = 512
    deadline_ms: int = 300000
    lease_ms: int = 30000
    queue_depth: int = 4096
    tenant_depth: int = 128
    active_per_tenant: int = 2

    def __post_init__(self):
        for name, low, high in (
            ("input_bytes",1,1048576),
            ("output_tokens",1,32768),
            ("deadline_ms",100,3600000),
            ("lease_ms",100,300000),
            ("queue_depth",1,100000),
            ("tenant_depth",1,4096),
            ("active_per_tenant",1,128),
        ):
            require_int(getattr(self,name),low,high,name)
        if self.tenant_depth > self.queue_depth:
            deny("limit-tenant-over-global")
        if self.active_per_tenant > self.tenant_depth:
            deny("limit-active-over-depth")


@dataclass(frozen=True, slots=True)
class JobSpec:
    job_id: str
    request_id: str
    owner: JobIdentity
    question: str
    created_ms: int
    expires_ms: int
    priority: int = 0
    dependencies: tuple[str,...] = ()

    def __post_init__(self):
        require_id(self.job_id,"job")
        require_id(self.request_id,"request")
        if type(self.owner) is not JobIdentity:
            deny("job-owner")
        require_text(self.question, 32768, "question")
        if len(self.question.encode("utf-8")) > 65536:
            deny("job-question-bytes")
        require_int(self.created_ms,0,2**63-1,"created")
        require_int(self.expires_ms,0,2**63-1,"expires")
        if not self.created_ms < self.expires_ms <= self.created_ms + 3600000:
            deny("job-expiration")
        require_int(self.priority,0,3,"priority")
        if type(self.dependencies) is not tuple or len(self.dependencies)>32:
            deny("job-dependencies")
        if len(set(self.dependencies)) != len(self.dependencies):
            deny("job-duplicate-dependencies")
        for item in self.dependencies:
            require_id(item,"dependency")
            if item == self.job_id:
                deny("job-self-dependency")

    @property
    def digest(self) -> str:
        return fingerprint(self.to_record())

    def to_record(self) -> dict:
        return {
            "schema":"skeleton.ai.durable-job.v1","job_id":self.job_id,
            "request_id":self.request_id,"owner":self.owner.to_record(),
            "question":self.question,"created_ms":self.created_ms,
            "expires_ms":self.expires_ms,"priority":self.priority,
            "dependencies":list(self.dependencies),
        }
