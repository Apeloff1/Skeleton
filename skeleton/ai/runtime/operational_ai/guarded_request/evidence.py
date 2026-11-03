"""Source-bound citation proof; byte offsets never silently become text offsets."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .errors import deny
from .model_pins import require_sha256
from .identities import require_id


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    source_sha256: str
    begin: int
    end: int
    passage: str

    def __post_init__(self) -> None:
        require_id(self.source_id, "source")
        require_sha256(self.source_sha256)
        if type(self.begin) is not int or type(self.end) is not int:
            deny("citation-offset")
        if self.begin < 0 or self.end <= self.begin or self.end - self.begin > 65536:
            deny("citation-offset")
        if type(self.passage) is not str or not self.passage or len(self.passage.encode("utf-8")) > 65536:
            deny("citation-passage")

    def verify(self, source: bytes) -> None:
        if type(source) is not bytes or len(source) > 16 * 1024 * 1024:
            deny("source-bounds")
        if not hmac.compare_digest(hashlib.sha256(source).hexdigest(), self.source_sha256):
            deny("source-digest")
        if self.end > len(source):
            deny("citation-offset")
        try:
            actual = source[self.begin:self.end].decode("utf-8", errors="strict")
        except UnicodeError:
            deny("citation-boundary")
        if actual != self.passage:
            deny("citation-mismatch")
