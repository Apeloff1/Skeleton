"""Deterministic redaction for shell-plane audit and diagnostic data."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

_DEFAULT_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "private_key",
    }
)

_DEFAULT_PATTERNS = (
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@",
    r"(?i)\b(?:token|secret|password|passwd|api[_-]?key)\s*[=:]\s*[^\s,;]+",
)


@dataclass(frozen=True)
class RedactionRule:
    pattern: str
    replacement: str = "[REDACTED]"
    flags: int = 0

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


@dataclass(frozen=True)
class RedactionPolicy:
    secret_keys: frozenset[str] = _DEFAULT_SECRET_KEYS
    rules: tuple[RedactionRule, ...] = field(
        default_factory=lambda: tuple(RedactionRule(pattern) for pattern in _DEFAULT_PATTERNS)
    )
    replacement: str = "[REDACTED]"
    max_string_chars: int = 4096
    max_collection_items: int = 128
    max_depth: int = 12

    def __post_init__(self) -> None:
        if self.max_string_chars <= 0 or self.max_collection_items <= 0 or self.max_depth <= 0:
            raise ValueError("redaction bounds must be positive")
        object.__setattr__(self, "secret_keys", frozenset(key.casefold() for key in self.secret_keys))
        object.__setattr__(self, "rules", tuple(self.rules))
        for rule in self.rules:
            rule.compile()


class SecretRedactor:
    """Redact sensitive strings and structured values without mutating inputs."""

    def __init__(self, policy: RedactionPolicy | None = None) -> None:
        self.policy = policy or RedactionPolicy()
        self._compiled = tuple((rule.compile(), rule.replacement) for rule in self.policy.rules)

    @staticmethod
    def _normalized_key(key: object) -> str:
        return str(key).strip().casefold().replace("-", "_")

    def redact_text(self, value: str) -> str:
        text = value
        for pattern, replacement in self._compiled:
            text = pattern.sub(replacement, text)
        if len(text) > self.policy.max_string_chars:
            suffix = f"…[TRUNCATED {len(text) - self.policy.max_string_chars} chars]"
            text = text[: self.policy.max_string_chars] + suffix
        return text

    def redact(self, value: Any, *, _depth: int = 0, _key: object | None = None) -> Any:
        if _depth >= self.policy.max_depth:
            return "[DEPTH-LIMIT]"
        if _key is not None and self._normalized_key(_key) in self.policy.secret_keys:
            return self.policy.replacement
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, bytes):
            return f"[BYTES {len(value)}]"
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for index, (key, child) in enumerate(value.items()):
                if index >= self.policy.max_collection_items:
                    result["[TRUNCATED]"] = len(value) - self.policy.max_collection_items
                    break
                label = self.redact_text(str(key))
                result[label] = self.redact(child, _depth=_depth + 1, _key=key)
            return result
        if isinstance(value, (list, tuple)):
            items = [
                self.redact(child, _depth=_depth + 1)
                for child in value[: self.policy.max_collection_items]
            ]
            if len(value) > self.policy.max_collection_items:
                items.append(f"[TRUNCATED {len(value) - self.policy.max_collection_items} items]")
            return items if isinstance(value, list) else tuple(items)
        if isinstance(value, (set, frozenset)):
            rendered = sorted(self.redact_text(str(child)) for child in value)
            return rendered[: self.policy.max_collection_items]
        return self.redact_text(repr(value))

    def redact_mapping(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        redacted = self.redact(value)
        assert isinstance(redacted, dict)
        return MappingProxyType(redacted)

    def add_literals(self, literals: Iterable[str]) -> "SecretRedactor":
        rules = list(self.policy.rules)
        for literal in literals:
            if literal:
                rules.insert(0, RedactionRule(re.escape(literal), self.policy.replacement))
        return SecretRedactor(
            RedactionPolicy(
                secret_keys=self.policy.secret_keys,
                rules=tuple(rules),
                replacement=self.policy.replacement,
                max_string_chars=self.policy.max_string_chars,
                max_collection_items=self.policy.max_collection_items,
                max_depth=self.policy.max_depth,
            )
        )
