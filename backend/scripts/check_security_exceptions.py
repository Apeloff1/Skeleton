"""Fail-closed validator for repository security exceptions.

Security exceptions are allowed only when they are explicit, narrow, reviewed,
and time-bounded. The registry is intentionally data-only; security scanners do
not silently infer or manufacture exceptions from comments or labels.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / ".github" / "security" / "security-exceptions.json"
SCHEMA = 1
MAX_EXCEPTIONS = 100
MAX_SCOPE_ITEMS = 16
MAX_DURATION_DAYS = 30
MAX_TEXT = 1024

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,63}$")
CONTROL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]{2,127}$")
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{1,127}$")
EXPECTED_ENTRY_KEYS = frozenset(
    {
        "id",
        "control",
        "scope",
        "reason",
        "compensating_control",
        "owner",
        "tracking_issue",
        "review_pr",
        "approved_by",
        "starts_on",
        "expires_on",
    }
)


class SecurityExceptionPolicyError(ValueError):
    """Registry contents cannot satisfy the repository security policy."""


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecurityExceptionPolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SecurityExceptionPolicyError(
            f"cannot read security exception registry: {path}"
        ) from exc
    try:
        payload = json.loads(text, object_pairs_hook=_no_duplicate_object)
    except SecurityExceptionPolicyError:
        raise
    except json.JSONDecodeError as exc:
        raise SecurityExceptionPolicyError(
            f"invalid security exception JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise SecurityExceptionPolicyError("security exception registry must be an object")
    return payload


def _required_text(value: Any, *, field: str, minimum: int = 2) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise SecurityExceptionPolicyError(f"{field} must be a trimmed string")
    if len(value) < minimum or len(value) > MAX_TEXT:
        raise SecurityExceptionPolicyError(f"{field} length is outside policy bounds")
    if "\x00" in value or "\r" in value:
        raise SecurityExceptionPolicyError(f"{field} contains unsafe characters")
    return value


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SecurityExceptionPolicyError(f"{field} must be a positive integer")
    return value


def _parse_date(value: Any, *, field: str) -> date:
    text = _required_text(value, field=field, minimum=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise SecurityExceptionPolicyError(
            f"{field} must be an ISO date YYYY-MM-DD"
        ) from exc
    if parsed.isoformat() != text:
        raise SecurityExceptionPolicyError(f"{field} must use canonical ISO date form")
    return parsed


def _validate_scope(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_SCOPE_ITEMS:
        raise SecurityExceptionPolicyError(
            "scope must be a non-empty bounded list of exact paths/components"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _required_text(raw, field="scope item")
        if item in seen:
            raise SecurityExceptionPolicyError(f"duplicate scope item: {item}")
        if "\n" in item:
            raise SecurityExceptionPolicyError("scope item cannot contain newlines")
        if item in {".", "/", "*", "**"}:
            raise SecurityExceptionPolicyError("scope cannot target the whole repository")
        if "*" in item or "?" in item or "[" in item or "]" in item:
            raise SecurityExceptionPolicyError(
                f"scope must be exact, not wildcarded: {item}"
            )
        if item.startswith("/") or item.endswith("/"):
            raise SecurityExceptionPolicyError(
                f"scope must be a normalized relative path/component: {item}"
            )
        parts = item.split("/")
        if ".." in parts or "." in parts:
            raise SecurityExceptionPolicyError(
                f"scope contains traversal-like segments: {item}"
            )
        seen.add(item)
        normalized.append(item)
    return tuple(sorted(normalized))


def _validate_reviewers(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 8:
        raise SecurityExceptionPolicyError(
            "approved_by must be a non-empty bounded reviewer list"
        )
    reviewers: list[str] = []
    seen: set[str] = set()
    for raw in value:
        reviewer = _required_text(raw, field="approved_by")
        if not IDENTITY_RE.fullmatch(reviewer):
            raise SecurityExceptionPolicyError(
                f"approved_by contains invalid identity: {reviewer}"
            )
        if reviewer in seen:
            raise SecurityExceptionPolicyError(
                f"duplicate approved_by identity: {reviewer}"
            )
        seen.add(reviewer)
        reviewers.append(reviewer)
    if not reviewers:
        raise SecurityExceptionPolicyError("security exception requires review evidence")
    return tuple(sorted(reviewers))


def validate_registry(
    payload: dict[str, Any],
    *,
    today: date | None = None,
) -> tuple[dict[str, Any], ...]:
    if set(payload) != {"schema", "exceptions"}:
        extra = sorted(set(payload) - {"schema", "exceptions"})
        missing = sorted({"schema", "exceptions"} - set(payload))
        raise SecurityExceptionPolicyError(
            f"registry keys mismatch; missing={missing} extra={extra}"
        )
    if payload["schema"] != SCHEMA:
        raise SecurityExceptionPolicyError(
            f"unsupported security exception schema: {payload['schema']!r}"
        )
    raw_entries = payload["exceptions"]
    if not isinstance(raw_entries, list):
        raise SecurityExceptionPolicyError("exceptions must be a list")
    if len(raw_entries) > MAX_EXCEPTIONS:
        raise SecurityExceptionPolicyError("too many active security exceptions")

    current = today or datetime.now(timezone.utc).date()
    validated: list[dict[str, Any]] = []
    ids: set[str] = set()

    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise SecurityExceptionPolicyError(
                f"exception {index} must be an object"
            )
        unknown = sorted(set(raw) - EXPECTED_ENTRY_KEYS)
        missing = sorted(EXPECTED_ENTRY_KEYS - set(raw))
        if unknown or missing:
            raise SecurityExceptionPolicyError(
                f"exception {index} keys mismatch; missing={missing} extra={unknown}"
            )

        exception_id = _required_text(raw["id"], field="id")
        if not ID_RE.fullmatch(exception_id):
            raise SecurityExceptionPolicyError(
                f"invalid exception id: {exception_id}"
            )
        if exception_id in ids:
            raise SecurityExceptionPolicyError(
                f"duplicate exception id: {exception_id}"
            )
        ids.add(exception_id)

        control = _required_text(raw["control"], field="control")
        if not CONTROL_RE.fullmatch(control):
            raise SecurityExceptionPolicyError(
                f"invalid control identifier: {control}"
            )

        scope = _validate_scope(raw["scope"])
        reason = _required_text(raw["reason"], field="reason", minimum=20)
        compensating = _required_text(
            raw["compensating_control"],
            field="compensating_control",
            minimum=20,
        )
        owner = _required_text(raw["owner"], field="owner")
        if not IDENTITY_RE.fullmatch(owner):
            raise SecurityExceptionPolicyError(f"invalid owner identity: {owner}")

        tracking_issue = _positive_int(raw["tracking_issue"], field="tracking_issue")
        review_pr = _positive_int(raw["review_pr"], field="review_pr")
        approved_by = _validate_reviewers(raw["approved_by"])

        starts_on = _parse_date(raw["starts_on"], field="starts_on")
        expires_on = _parse_date(raw["expires_on"], field="expires_on")
        if starts_on > current:
            raise SecurityExceptionPolicyError(
                f"{exception_id} starts in the future"
            )
        if expires_on < starts_on:
            raise SecurityExceptionPolicyError(
                f"{exception_id} expires before it starts"
            )
        lifetime = (expires_on - starts_on).days
        if lifetime > MAX_DURATION_DAYS:
            raise SecurityExceptionPolicyError(
                f"{exception_id} exceeds {MAX_DURATION_DAYS}-day maximum lifetime"
            )
        if expires_on < current:
            raise SecurityExceptionPolicyError(
                f"{exception_id} expired on {expires_on.isoformat()}"
            )

        validated.append(
            {
                "id": exception_id,
                "control": control,
                "scope": scope,
                "reason": reason,
                "compensating_control": compensating,
                "owner": owner,
                "tracking_issue": tracking_issue,
                "review_pr": review_pr,
                "approved_by": approved_by,
                "starts_on": starts_on,
                "expires_on": expires_on,
            }
        )

    return tuple(validated)


def validate_file(
    path: Path = DEFAULT_REGISTRY,
    *,
    today: date | None = None,
) -> tuple[dict[str, Any], ...]:
    return validate_registry(load_registry(path), today=today)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry",
        nargs="?",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="security exception registry path",
    )
    parser.add_argument(
        "--today",
        help="validation date override for deterministic replay/testing",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _argument_parser().parse_args(list(argv) if argv is not None else None)
    current: date | None = None
    if args.today:
        try:
            current = date.fromisoformat(args.today)
        except ValueError as exc:
            raise SystemExit(f"invalid --today date: {args.today}") from exc

    try:
        entries = validate_file(args.registry, today=current)
    except SecurityExceptionPolicyError as exc:
        print(f"security exception policy violation: {exc}")
        return 1

    if not entries:
        print("security exception policy: no active exceptions")
        return 0

    nearest = min(entry["expires_on"] for entry in entries)
    print(
        f"security exception policy: {len(entries)} active; "
        f"nearest expiry {nearest.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
