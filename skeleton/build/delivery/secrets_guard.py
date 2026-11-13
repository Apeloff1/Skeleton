"""Reject secret-looking values before they reach configs or manifests.

Environment configs may only reference secrets indirectly (``secret://name``)
so they can be resolved by the vault at deploy time. Literal credentials are
refused.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

SECRET_REF_RE = re.compile(r"^secret://[a-z0-9][a-z0-9._/-]{0,127}$")
SENSITIVE_KEY_RE = re.compile(r"(pass(word)?|secret|token|api[_-]?key|private[_-]?key|credential|auth)", re.I)
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("url-credentials", re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
)
ENTROPY_MIN_LENGTH = 24
ENTROPY_THRESHOLD = 4.0


@dataclass(frozen=True)
class SecretFinding:
    location: str
    rule: str


def shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(text)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def is_secret_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(SECRET_REF_RE.fullmatch(value))


def scan_value(location: str, key: str, value: Any) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    if not isinstance(value, str) or is_secret_ref(value):
        return findings
    for rule, pattern in _PATTERNS:
        if pattern.search(value):
            findings.append(SecretFinding(location, rule))
    if SENSITIVE_KEY_RE.search(key) and value and not value.startswith("${"):
        findings.append(SecretFinding(location, "sensitive-key-literal"))
    token = value.strip()
    if (
        len(token) >= ENTROPY_MIN_LENGTH
        and " " not in token
        and "/" not in token
        and shannon_entropy(token) >= ENTROPY_THRESHOLD
    ):
        findings.append(SecretFinding(location, "high-entropy"))
    return findings


def scan_mapping(data: Mapping[str, Any], *, root: str = "$") -> tuple[SecretFinding, ...]:
    out: list[SecretFinding] = []

    def walk(node: Any, path: str, key: str) -> None:
        if isinstance(node, Mapping):
            for k in sorted(node, key=str):
                walk(node[k], f"{path}.{k}", str(k))
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]", key)
        else:
            out.extend(scan_value(path, key, node))

    walk(data, root, "")
    return tuple(sorted(set(out), key=lambda f: (f.location, f.rule)))


def scan_text(name: str, text: str) -> tuple[SecretFinding, ...]:
    out: list[SecretFinding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule, pattern in _PATTERNS:
            if pattern.search(line):
                out.append(SecretFinding(f"{name}:{lineno}", rule))
    return tuple(out)


def assert_clean(findings: Iterable[SecretFinding]) -> None:
    items = list(findings)
    if items:
        from skeleton.build.delivery._util import DeliveryError

        summary = ", ".join(f"{f.location}({f.rule})" for f in items[:10])
        raise DeliveryError(f"secret-like values found: {summary}")
