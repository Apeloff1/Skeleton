"""Bounded native-format regex validation for local inference release.

A Python re.fullmatch on user-controlled patterns can hang on catastrophic
backtracking. Demand an installed timeout-aware regex engine and bound both
pattern and output. This is postflight verification, NOT native sampler proof.
"""

from __future__ import annotations

from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextError, SealedContextLimitError,
)

MAX_PATTERN_BYTES = 2048
MAX_OUTPUT_BYTES = 64 * 1024
REGEX_TIMEOUT_SECONDS = 0.05


def _compiler(pattern: str):
    if not isinstance(pattern, str) or not pattern:
        raise SealedContextError("regex delivery requires a nonempty pattern")
    try:
        wire = pattern.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SealedContextError("regex delivery pattern has invalid Unicode") from exc
    if len(wire) > MAX_PATTERN_BYTES:
        raise SealedContextLimitError("regex delivery pattern exceeds bounded budget")
    try:
        import regex as timeout_regex
    except ImportError as exc:
        raise SealedContextBoundaryError(
            "timeout-aware regex engine is required for regex delivery"
        ) from exc
    try:
        return timeout_regex.compile(pattern)
    except (timeout_regex.error, ValueError, OverflowError, RecursionError) as exc:
        raise SealedContextError("regex delivery pattern is invalid") from exc


def validate_delivery_regex(pattern: str | None) -> None:
    """Compile before model inference so invalid formats never consume tokens."""
    _compiler(pattern)


def match_delivery_regex(text: str, pattern: str | None) -> None:
    """Match with a hard time and byte cap; do not release on timeout."""
    if not isinstance(text, str):
        raise SealedContextError("regex delivery is not text")
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SealedContextError("regex delivery contains invalid Unicode") from exc
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise SealedContextLimitError("regex delivery output exceeds bounded budget")
    compiled = _compiler(pattern)
    try:
        matched = compiled.fullmatch(text, timeout=REGEX_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise SealedContextLimitError("regex delivery match exceeded CPU time limit") from exc
    except (ValueError, RecursionError, OverflowError) as exc:
        raise SealedContextError("regex delivery match failed closed") from exc
    if matched is None:
        raise SealedContextError("regex delivery failed constrained format")
