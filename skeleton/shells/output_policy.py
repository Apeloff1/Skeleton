"""Output classification, retention, and redaction policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re


class OutputClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


@dataclass(frozen=True)
class OutputRetention:
    classification: OutputClass
    retain_bytes: bool
    retain_digest: bool = True
    max_retained_bytes: int = 64 * 1024
    retention_seconds: float = 3600.0

    def __post_init__(self) -> None:
        if self.max_retained_bytes < 0:
            raise ValueError("max_retained_bytes may not be negative")
        if self.retention_seconds < 0:
            raise ValueError("retention_seconds may not be negative")


@dataclass(frozen=True)
class ClassifiedOutput:
    classification: OutputClass
    retained: bytes
    original_bytes: int
    digest: str
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification.value,
            "original_bytes": self.original_bytes,
            "retained_bytes": len(self.retained),
            "digest": self.digest,
            "truncated": self.truncated,
        }


class OutputClassifier:
    """Simple deterministic classification with configurable secret patterns."""

    def __init__(
        self,
        *,
        secret_patterns: tuple[str, ...] = (),
        sensitive_patterns: tuple[str, ...] = (),
    ) -> None:
        self._secret = tuple(re.compile(pattern, re.IGNORECASE) for pattern in secret_patterns)
        self._sensitive = tuple(re.compile(pattern, re.IGNORECASE) for pattern in sensitive_patterns)

    def classify(self, data: bytes) -> OutputClass:
        text = data.decode("utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in self._secret):
            return OutputClass.SECRET
        if any(pattern.search(text) for pattern in self._sensitive):
            return OutputClass.SENSITIVE
        return OutputClass.INTERNAL


class OutputRetentionPolicy:
    def __init__(
        self,
        rules: dict[OutputClass, OutputRetention] | None = None,
    ) -> None:
        self.rules = rules or {
            OutputClass.PUBLIC: OutputRetention(OutputClass.PUBLIC, True, True, 256 * 1024, 86400),
            OutputClass.INTERNAL: OutputRetention(OutputClass.INTERNAL, True, True, 64 * 1024, 3600),
            OutputClass.SENSITIVE: OutputRetention(OutputClass.SENSITIVE, False, True, 0, 3600),
            OutputClass.SECRET: OutputRetention(OutputClass.SECRET, False, True, 0, 0),
        }
        missing = set(OutputClass) - set(self.rules)
        if missing:
            raise ValueError("output retention rules must cover every classification")

    def apply(self, data: bytes, classification: OutputClass) -> ClassifiedOutput:
        rule = self.rules[classification]
        retained = b""
        truncated = False
        if rule.retain_bytes:
            retained = data[: rule.max_retained_bytes]
            truncated = len(data) > len(retained)
        return ClassifiedOutput(
            classification=classification,
            retained=retained,
            original_bytes=len(data),
            digest=hashlib.sha256(data).hexdigest() if rule.retain_digest else "",
            truncated=truncated,
        )
