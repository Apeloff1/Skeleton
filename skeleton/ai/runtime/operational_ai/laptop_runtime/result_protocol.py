"""Native-commit receipt shape and hash check before network publication."""
from __future__ import annotations
import hashlib
from .contracts import exact,identity_hash,nonnegative,utf8,refuse

def verify_turn_receipt(value,*,model_sha256,tokenizer_sha256):
    if type(value) is not dict:refuse("authoritative turn receipt required")
    required={"model_sha256","tokenizer_sha256","output_sha256","text",
              "prompt_tokens","generated_tokens","replayed"}
    if not required.issubset(value):refuse("native receipt fields absent")
    if identity_hash(value["model_sha256"])!=model_sha256:
        refuse("receipt model identity differs from active backend")
    if identity_hash(value["tokenizer_sha256"])!=tokenizer_sha256:
        refuse("receipt tokenizer identity differs from active backend")
    raw=utf8(value["text"],maximum=262144).encode("utf-8")
    if hashlib.sha256(raw).hexdigest()!=identity_hash(value["output_sha256"]):
        refuse("authoritative response digest mismatch")
    nonnegative(value["prompt_tokens"],maximum=131072)
    nonnegative(value["generated_tokens"],maximum=8192)
    if type(value["replayed"]) is not bool:refuse("explicit replay flag required")
    return value
