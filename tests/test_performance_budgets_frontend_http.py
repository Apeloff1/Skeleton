"""Drift check: frontend HTTP bounds in code must match PERFORMANCE_BUDGETS.md."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = (ROOT / "frontend" / "src" / "utils" / "requestRecoveryPolicy.ts").read_text()
DOC = (ROOT / "docs" / "engineering" / "PERFORMANCE_BUDGETS.md").read_text()


def _fn(name: str) -> str:
    m = re.search(rf"export function {name}\b.*?\n}}", POLICY, re.S)
    assert m, name
    return m.group(0)


def _row(label: str) -> str:
    m = re.search(rf"^\| {re.escape(label)} \| ([^|]+) \|", DOC, re.M)
    assert m, f"PERFORMANCE_BUDGETS.md missing row {label!r}"
    return m.group(1).strip()


def test_response_size_bounds_match_doc():
    body = _fn("boundedResponseChars")
    assert "const fallback = 8 * 1024 * 1024;" in body
    assert "Math.min(64 * 1024 * 1024, Math.max(1024," in body
    assert _row("JSON response size (default)") == "8 MiB"
    assert _row("JSON response size (hard ceiling)") == "64 MiB"
    assert _row("JSON response size (floor)") == "1 KiB"


def test_timeout_and_retry_bounds_match_doc():
    assert "export const MAX_RETRIES = 3;" in POLICY
    assert "export const MIN_TIMEOUT_MS = 250;" in POLICY
    assert "export const MAX_TIMEOUT_MS = 30_000;" in POLICY
    assert "return 12_000;" in _fn("boundedTimeoutMs")
    assert _row("Request timeout (default / min / max)") == "12 s / 250 ms / 30 s"
    assert _row("Retries (safe methods, max)") == "3"
