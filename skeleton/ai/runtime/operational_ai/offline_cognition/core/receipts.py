"""Typed committed outputs, content SHA and bounded native token accounting."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import Scope,identifier,sha,integer,text,hash_bytes,refuse,fingerprint
@dataclass(frozen=True,slots=True)
class NativeReceipt:
    scope:Scope
    session_id:str
    request_id:str
    text:str
    output_sha256:str
    input_tokens:int
    output_tokens:int
    replayed:bool
    def __post_init__(self):
        if type(self.scope) is not Scope:refuse("source model identity required")
        identifier(self.session_id);identifier(self.request_id)
        text(self.text,maximum=262144)
        if hash_bytes(self.text.encode("utf-8"))!=sha(self.output_sha256):
            refuse("native receipt output hash mismatch")
        integer(self.input_tokens,minimum=0,maximum=262144)
        integer(self.output_tokens,minimum=0,maximum=8192)
        if type(self.replayed) is not bool:refuse("actual replay flag required")
    def claims(self):
        return {"scope":self.scope.receipt(),"session_id":self.session_id,
                "request_id":self.request_id,"output_sha256":self.output_sha256,
                "input_tokens":self.input_tokens,"output_tokens":self.output_tokens,
                "replayed":self.replayed}
    def digest(self):return fingerprint(self.claims())
def from_supervisor(scope,session_id,request_id,output):
    if type(output) is not dict:refuse("canonical supervisor receipt object required")
    expected={"model_sha256","tokenizer_sha256","text","output_sha256",
              "prompt_tokens","generated_tokens","replayed"}
    if not expected.issubset(output):refuse("missing authoritative output evidence")
    if output["model_sha256"]!=scope.model_sha256 or output["tokenizer_sha256"]!=scope.tokenizer_sha256:
        refuse("output model/tokenizer epoch drift")
    return NativeReceipt(scope,session_id,request_id,output["text"],
                         output["output_sha256"],output["prompt_tokens"],
                         output["generated_tokens"],output["replayed"])
