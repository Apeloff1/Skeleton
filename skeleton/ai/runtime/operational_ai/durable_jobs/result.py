"""Verified native inference receipt contract and canonical digest binding."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import fingerprint, require_int, require_sha, require_text
from .errors import deny


@dataclass(frozen=True, slots=True)
class JobResult:
    text: str
    output_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    prompt_tokens: int
    generated_tokens: int
    original_request_id: str

    def __post_init__(self):
        require_text(self.text,262144,"output",allow_empty=True)
        if len(self.text.encode("utf-8")) > 262144:
            deny("output-bytes")
        for name in ("output_sha256","model_sha256","tokenizer_sha256"):
            require_sha(getattr(self,name))
        for name in ("prompt_tokens","generated_tokens"):
            require_int(getattr(self,name),0,262144,name)
        from .spec import require_id
        require_id(self.original_request_id,"result-request")
        from .canonical import sha256
        if sha256(self.text.encode("utf-8")) != self.output_sha256:
            deny("output-digest-mismatch")

    def to_record(self):
        return {
            "schema":"skeleton.ai.durable-result.v1",
            "text":self.text,"output_sha256":self.output_sha256,
            "model_sha256":self.model_sha256,
            "tokenizer_sha256":self.tokenizer_sha256,
            "prompt_tokens":self.prompt_tokens,"generated_tokens":self.generated_tokens,
            "original_request_id":self.original_request_id,
        }

    @property
    def digest(self):
        return fingerprint(self.to_record())
