from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / ".github" / "ci" / "flaky-quarantine.json"
MAX_QUARANTINE_DAYS = 30
ISSUE_RE = re.compile(r"^(?:#\d+|https://github\.com/[^/]+/[^/]+/issues/\d+)$")


def _fail(message: str) -> None:
    raise SystemExit(f"flaky quarantine policy error: {message}")


def main() -> None:
    try:
        payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(f"missing registry: {REGISTRY.relative_to(REPO_ROOT)}")
    except json.JSONDecodeError as exc:
        _fail(f"invalid JSON: line {exc.lineno}, column {exc.colno}")

    if not isinstance(payload, dict):
        _fail("registry root must be an object")
    if payload.get("schema_version") != 1:
        _fail("schema_version must be exactly 1")

    entries = payload.get("entries")
    if not isinstance(entries, list):
        _fail("entries must be a list")

    today = date.today()
    latest_allowed = today + timedelta(days=MAX_QUARANTINE_DAYS)
    seen_tests: set[str] = set()

    required = {"test", "issue", "owner", "expires", "reason"}
    allowed = required | {"non_blocking_check"}

    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            _fail(f"{label} must be an object")

        missing = sorted(required - set(entry))
        unknown = sorted(set(entry) - allowed)
        if missing:
            _fail(f"{label} missing required fields: {', '.join(missing)}")
        if unknown:
            _fail(f"{label} has unknown fields: {', '.join(unknown)}")

        test = entry["test"]
        if not isinstance(test, str) or not test.strip():
            _fail(f"{label}.test must be a non-empty exact test/check identifier")
        test = test.strip()
        if test in seen_tests:
            _fail(f"duplicate quarantine entry for {test!r}")
        seen_tests.add(test)

        issue = entry["issue"]
        if not isinstance(issue, str) or ISSUE_RE.fullmatch(issue.strip()) is None:
            _fail(f"{label}.issue must be #<number> or a GitHub issue URL")

        owner = entry["owner"]
        if not isinstance(owner, str) or not owner.startswith("@") or len(owner) < 2:
            _fail(f"{label}.owner must be an explicit @owner")

        reason = entry["reason"]
        if not isinstance(reason, str) or len(reason.strip()) < 10:
            _fail(f"{label}.reason must explain the quarantine")

        non_blocking = entry.get("non_blocking_check")
        if non_blocking is not None and (
            not isinstance(non_blocking, str) or not non_blocking.strip()
        ):
            _fail(f"{label}.non_blocking_check must be a non-empty check name")

        expires_raw = entry["expires"]
        if not isinstance(expires_raw, str):
            _fail(f"{label}.expires must be an ISO date (YYYY-MM-DD)")
        try:
            expires = date.fromisoformat(expires_raw)
        except ValueError:
            _fail(f"{label}.expires must be an ISO date (YYYY-MM-DD)")

        if expires < today:
            _fail(f"{test!r} quarantine expired on {expires.isoformat()}")
        if expires > latest_allowed:
            _fail(
                f"{test!r} quarantine expires too far in the future; "
                f"maximum is {MAX_QUARANTINE_DAYS} days"
            )

    print(f"flaky quarantine registry valid: {len(entries)} active entr{'y' if len(entries) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
