"""Grounded deterministic acceptance assertions (not a semantic judge)."""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
from typing import Any

from .canonical import decode, encode, integer, text
from .errors import deny

TYPES = frozenset({
    "exact", "casefold_exact", "contains", "not_contains", "one_of", "json_equals",
    "json_field", "regex_full", "numeric_exact", "starts_with", "ends_with",
    "max_words", "min_words", "no_secret", "citation_label",
})
MAX_CHECKS = 12


@dataclass(frozen=True, slots=True)
class Check:
    kind: str
    expected: Any
    key: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in TYPES:
            deny("check-kind")
        if self.key is not None:
            text(self.key, "check-key", 128)
        encode(self.expected)
        if self.kind in ("exact", "casefold_exact", "contains", "not_contains",
                         "regex_full", "starts_with", "ends_with", "no_secret",
                         "citation_label"):
            text(self.expected, "check-text", 2048)
        if self.kind in ("max_words", "min_words"):
            integer(self.expected, "check-word-count", 0, 4096)
        if self.kind == "one_of":
            if type(self.expected) not in (list, tuple) or not 1 <= len(self.expected) <= 24:
                deny("check-options")
            for option in self.expected:
                text(option, "check-option", 2048)
        if self.kind == "json_field" and self.key is None:
            deny("check-json-field-key")
        if self.kind == "numeric_exact" and (type(self.expected) not in (int, float)
                                            or not math.isfinite(self.expected)):
            deny("check-numeric")
        if self.kind == "regex_full":
            if len(self.expected) > 128:
                deny("check-regex-size")
            # No user-provided complex regex: corpus recipes use only small anchored forms.
            try:
                re.compile(self.expected)
            except re.error:
                deny("check-regex-invalid")

    @classmethod
    def from_json(cls, value: Any) -> "Check":
        if type(value) is not dict or set(value) - {"kind", "expected", "key"}:
            deny("check-schema")
        return cls(kind=value.get("kind"), expected=value.get("expected"),
                   key=value.get("key"))

    def record(self) -> dict:
        data = {"kind": self.kind, "expected": self.expected}
        if self.key is not None:
            data["key"] = self.key
        return data


@dataclass(frozen=True, slots=True)
class Result:
    kind: str
    passed: bool
    diagnostic: str


def _words(value: str) -> list[str]:
    return value.strip().split()


def _json_field(obj: Any, path: str) -> Any:
    if type(obj) is not dict or not path:
        return None
    for seg in path.split("."):
        if type(obj) is not dict or seg not in obj:
            return None
        obj = obj[seg]
    return obj


def evaluate(check: Check, response: str) -> Result:
    if type(response) is not str or len(response) > 262144:
        deny("response-invalid")
    norm = response.strip()
    wanted = check.expected
    passed = False
    diagnostic = "comparison-failed"
    if check.kind == "exact":
        passed = norm == wanted
    elif check.kind == "casefold_exact":
        passed = norm.casefold() == wanted.casefold()
    elif check.kind == "contains":
        passed = wanted in norm
    elif check.kind == "not_contains":
        passed = wanted not in norm
    elif check.kind == "one_of":
        passed = norm in wanted
    elif check.kind == "json_equals":
        try:
            parsed = decode(norm)
            passed = encode(parsed) == encode(wanted)
        except ValueError:
            diagnostic = "invalid-json-output"
    elif check.kind == "json_field":
        try:
            parsed = decode(norm)
            passed = _json_field(parsed, check.key) == wanted
        except ValueError:
            diagnostic = "invalid-json-output"
    elif check.kind == "regex_full":
        # Existing corpus regex only; fullmatch restricts off-format output.
        passed = re.fullmatch(wanted, norm, flags=re.ASCII) is not None
    elif check.kind == "numeric_exact":
        try:
            number = float(norm)
            passed = math.isfinite(number) and number == wanted
        except ValueError:
            diagnostic = "invalid-numeric-output"
    elif check.kind == "starts_with":
        passed = norm.startswith(wanted)
    elif check.kind == "ends_with":
        passed = norm.endswith(wanted)
    elif check.kind == "max_words":
        passed = len(_words(norm)) <= wanted
    elif check.kind == "min_words":
        passed = len(_words(norm)) >= wanted
    elif check.kind == "no_secret":
        passed = wanted not in norm
    elif check.kind == "citation_label":
        passed = wanted in norm and re.search(r"\[" + re.escape(wanted) + r"\]", norm) is not None
    return Result(check.kind, bool(passed), "match" if passed else diagnostic)
