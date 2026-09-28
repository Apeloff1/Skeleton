"""Fail-closed governance for temporary security exceptions."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / ".github" / "ci" / "security-exceptions.json"
MAX_REGISTRY_BYTES = 128 * 1024
MAX_ENTRIES = 100
MAX_PATHS = 16
MAX_TEXT = 1024
MAX_EXCEPTION_DAYS = 30

ENTRY_KEYS = frozenset(
    {
        "id",
        "control",
        "paths",
        "reason",
        "compensating_control",
        "owner",
        "tracking_issue",
        "approved_by",
        "approved_on",
        "expires_on",
    }
)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
GITHUB_LOGIN_RE = re.compile(r"^@?[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
FORBIDDEN_PATH_CHARS = frozenset("*?[]{}!")


class SecurityExceptionPolicyError(ValueError):
    """Raised when exception governance cannot be proven safe."""


def _object_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecurityExceptionPolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise SecurityExceptionPolicyError(f"cannot stat registry: {path}") from exc
    if size > MAX_REGISTRY_BYTES:
        raise SecurityExceptionPolicyError(
            f"registry exceeds {MAX_REGISTRY_BYTES} byte limit"
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecurityExceptionPolicyError(f"cannot read registry: {path}") from exc
    try:
        payload = json.loads(raw, object_pairs_hook=_object_pairs_no_duplicates)
    except SecurityExceptionPolicyError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SecurityExceptionPolicyError("registry is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise SecurityExceptionPolicyError("registry root must be an object")
    return payload


def _require_exact_keys(payload: dict[str, Any], expected: frozenset[str], field: str) -> None:
    actual = frozenset(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise SecurityExceptionPolicyError(
            f"{field} keys mismatch; missing={missing}, extra={extra}"
        )


def _text(value: Any, field: str, *, max_length: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise SecurityExceptionPolicyError(f"{field} must be a string")
    if not value or value != value.strip():
        raise SecurityExceptionPolicyError(f"{field} must be a non-empty trimmed string")
    if len(value) > max_length:
        raise SecurityExceptionPolicyError(f"{field} exceeds {max_length} characters")
    if "\x00" in value or "\r" in value:
        raise SecurityExceptionPolicyError(f"{field} contains unsafe control characters")
    return value


def _login(value: Any, field: str) -> str:
    login = _text(value, field, max_length=40)
    if not GITHUB_LOGIN_RE.fullmatch(login):
        raise SecurityExceptionPolicyError(f"{field} is not a valid GitHub-style login")
    return login


def _parse_date(value: Any, field: str) -> date:
    text = _text(value, field, max_length=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise SecurityExceptionPolicyError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise SecurityExceptionPolicyError(f"{field} must be canonical YYYY-MM-DD")
    return parsed


def _path_scope(value: Any, field: str) -> str:
    scope = _text(value, field, max_length=256)
    if "\\" in scope or any(char in scope for char in FORBIDDEN_PATH_CHARS):
        raise SecurityExceptionPolicyError(
            f"{field} must be an exact repository path/component without globs"
        )
    path = PurePosixPath(scope)
    if path.is_absolute() or scope in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
        raise SecurityExceptionPolicyError(f"{field} must stay within the repository")
    if len(path.parts) == 1 and path.parts[0] in {"backend", "frontend", "skeleton", "scripts", ".github"}:
        raise SecurityExceptionPolicyError(
            f"{field} is too broad; name a narrower path/component"
        )
    return scope


def validate_registry(payload: dict[str, Any], *, today: date) -> tuple[str, ...]:
    _require_exact_keys(payload, frozenset({"schema_version", "entries"}), "registry")
    if payload["schema_version"] != 1:
        raise SecurityExceptionPolicyError("schema_version must equal 1")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise SecurityExceptionPolicyError("entries must be a list")
    if len(entries) > MAX_ENTRIES:
        raise SecurityExceptionPolicyError(f"entries exceed {MAX_ENTRIES} item limit")

    seen_ids: set[str] = set()
    active: list[str] = []
    for index, raw in enumerate(entries):
        field = f"entries[{index}]"
        if not isinstance(raw, dict):
            raise SecurityExceptionPolicyError(f"{field} must be an object")
        _require_exact_keys(raw, ENTRY_KEYS, field)

        exception_id = _text(raw["id"], f"{field}.id", max_length=64)
        if not ID_RE.fullmatch(exception_id):
            raise SecurityExceptionPolicyError(f"{field}.id has invalid format")
        if exception_id in seen_ids:
            raise SecurityExceptionPolicyError(f"duplicate exception id: {exception_id}")
        seen_ids.add(exception_id)

        _text(raw["control"], f"{field}.control", max_length=160)
        _text(raw["reason"], f"{field}.reason")
        _text(raw["compensating_control"], f"{field}.compensating_control")
        _login(raw["owner"], f"{field}.owner")
        _login(raw["approved_by"], f"{field}.approved_by")

        issue = raw["tracking_issue"]
        if isinstance(issue, bool) or not isinstance(issue, int) or issue <= 0:
            raise SecurityExceptionPolicyError(f"{field}.tracking_issue must be a positive issue number")

        paths = raw["paths"]
        if not isinstance(paths, list) or not paths:
            raise SecurityExceptionPolicyError(f"{field}.paths must be a non-empty list")
        if len(paths) > MAX_PATHS:
            raise SecurityExceptionPolicyError(f"{field}.paths exceeds {MAX_PATHS} scopes")
        normalized_paths = [_path_scope(item, f"{field}.paths") for item in paths]
        if len(set(normalized_paths)) != len(normalized_paths):
            raise SecurityExceptionPolicyError(f"{field}.paths contains duplicates")

        approved_on = _parse_date(raw["approved_on"], f"{field}.approved_on")
        expires_on = _parse_date(raw["expires_on"], f"{field}.expires_on")
        if approved_on > today:
            raise SecurityExceptionPolicyError(f"{field}.approved_on is in the future")
        if expires_on <= approved_on:
            raise SecurityExceptionPolicyError(f"{field}.expires_on must be after approved_on")
        duration = (expires_on - approved_on).days
        if duration > MAX_EXCEPTION_DAYS:
            raise SecurityExceptionPolicyError(
                f"{field} lasts {duration} days; maximum is {MAX_EXCEPTION_DAYS}"
            )
        if today >= expires_on:
            raise SecurityExceptionPolicyError(
                f"{field} expired on {expires_on.isoformat()}"
            )
        active.append(exception_id)

    return tuple(active)


def validate_file(path: Path = DEFAULT_REGISTRY, *, today: date | None = None) -> tuple[str, ...]:
    effective_today = today or datetime.now(timezone.utc).date()
    return validate_registry(_load_json(path), today=effective_today)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--today", type=date.fromisoformat)
    args = parser.parse_args()
    try:
        active = validate_file(args.registry, today=args.today)
    except (SecurityExceptionPolicyError, OSError) as exc:
        print(f"Security exception policy violation: {exc}")
        return 1
    print(f"Security exception registry OK: {len(active)} active exception(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
