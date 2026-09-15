"""Fail CI when the frontend Docker build context can include credential material."""
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DOCKERIGNORE = REPO_ROOT / "frontend" / ".dockerignore"

# Keep these explicit rather than relying on broad wildcard coverage. Each rule
# protects a credential family that is common in local developer environments.
REQUIRED_RULES: tuple[str, ...] = (
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    "credentials*.json",
    "service-account*.json",
)

# Dockerignore negations re-include files and therefore deserve explicit review.
# The public example environment file is the only intentional exception today.
ALLOWED_NEGATIONS = frozenset({"!.env.example"})


def _label(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def active_rules(path: Path) -> tuple[str, ...]:
    """Return non-comment Dockerignore rules in source order."""
    text = path.read_text(encoding="utf-8")
    return tuple(
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )


def violations(path: Path = FRONTEND_DOCKERIGNORE) -> list[str]:
    """Return fail-closed policy findings for the frontend Docker context."""
    label = _label(path)
    try:
        rules = active_rules(path)
    except (OSError, UnicodeError) as exc:
        return [f"{label}: read failure: {type(exc).__name__}"]

    rule_set = set(rules)
    findings = [
        f"{label}: missing required secret exclusion: {rule}"
        for rule in REQUIRED_RULES
        if rule not in rule_set
    ]

    findings.extend(
        f"{label}: unapproved Dockerignore negation: {rule}"
        for rule in rules
        if rule.startswith("!") and rule not in ALLOWED_NEGATIONS
    )
    return findings


def main() -> int:
    findings = violations()
    if findings:
        print("Frontend Docker secret-boundary policy failed:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("Frontend Docker secret-boundary policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
