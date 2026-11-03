"""Strict model and tokenizer identity; only approved local bytes are used."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
from typing import Any

from .errors import deny
from .identities import require_id

_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def require_sha256(value: Any) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        deny("digest-invalid")
    return value


@dataclass(frozen=True, slots=True)
class ModelPin:
    model_id: str
    model_sha256: str
    tokenizer_sha256: str
    exact_bytes: int
    license_id: str

    def __post_init__(self) -> None:
        require_id(self.model_id, "model")
        require_sha256(self.model_sha256)
        require_sha256(self.tokenizer_sha256)
        if type(self.exact_bytes) is not int or not 1 <= self.exact_bytes <= 2**35:
            deny("model-byte-size")
        if type(self.license_id) is not str or not 1 <= len(self.license_id) <= 128:
            deny("model-license")
        if not self.license_id.isascii() or not all(c.isalnum() or c in "-._" for c in self.license_id):
            deny("model-license")

    def verify(self, supplied: bytes, *, reported_tokenizer_sha256: str) -> None:
        require_sha256(reported_tokenizer_sha256)
        if type(supplied) is not bytes or len(supplied) != self.exact_bytes:
            deny("model-byte-size")
        if not hmac.compare_digest(self.model_sha256, hashlib.sha256(supplied).hexdigest()):
            deny("model-sha")
        if not hmac.compare_digest(reported_tokenizer_sha256, self.tokenizer_sha256):
            deny("tokenizer-sha")
