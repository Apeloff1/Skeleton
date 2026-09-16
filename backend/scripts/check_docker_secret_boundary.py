"""Enforce secret exclusions for Docker contexts that copy the repository broadly.

A Dockerfile that uses ``COPY . .`` sends the build context to the daemon before
any image-layer policy can help. This gate keeps the adjacent ``.dockerignore``
as an explicit, regression-tested security boundary for credential-shaped local
files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SECRET_EXCLUSIONS = frozenset(
    {
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "*.crt",
        "*.cer",
        "credentials*.json",
        "service-account*.json",
    }
)

REQUIRED_REINCLUSIONS = frozenset({"!.env.example"})
ALLOWED_REINCLUSIONS = REQUIRED_REINCLUSIONS

BROAD_COPY_RE = re.compile(
    r"^\s*(?:COPY|ADD)\s+(?:--\S+\s+)*\.\s+\.\s*(?:#.*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DockerContextPolicy:
    dockerfile: Path
    ignore_file: Path
    required_exclusions: frozenset[str] = REQUIRED_SECRET_EXCLUSIONS
    required_reinclusions: frozenset[str] = REQUIRED_REINCLUSIONS
    allowed_reinclusions: frozenset[str] = ALLOWED_REINCLUSIONS
    require_broad_copy: bool = True


POLICIES = (
    DockerContextPolicy(
        dockerfile=Path("frontend/Dockerfile"),
        ignore_file=Path("frontend/.dockerignore"),
    ),
)


def _safe_read(path: Path, *, label: str) -> tuple[str | None, list[str]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeError) as exc:
        return None, [f"{label}: read failure: {type(exc).__name__}"]


def _active_ignore_patterns(text: str) -> set[str]:
    return {
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    }


def policy_violations(
    policy: DockerContextPolicy,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    """Return sanitized violations for one Docker build-context policy."""
    dockerfile = repo_root / policy.dockerfile
    ignore_file = repo_root / policy.ignore_file

    docker_text, errors = _safe_read(dockerfile, label=str(policy.dockerfile))
    if errors:
        return errors
    assert docker_text is not None

    broad_copy_lines = [
        number
        for number, line in enumerate(docker_text.splitlines(), 1)
        if BROAD_COPY_RE.match(line)
    ]
    if policy.require_broad_copy and not broad_copy_lines:
        return [
            f"{policy.dockerfile}: expected broad Docker context copy is absent; "
            "review this guard with the Dockerfile change"
        ]
    if not broad_copy_lines:
        return []

    ignore_text, errors = _safe_read(ignore_file, label=str(policy.ignore_file))
    if errors:
        return errors
    assert ignore_text is not None

    patterns = _active_ignore_patterns(ignore_text)
    findings: list[str] = []
    copy_locations = ",".join(str(number) for number in broad_copy_lines)

    missing = sorted(policy.required_exclusions - patterns)
    findings.extend(
        f"{policy.ignore_file}: missing required secret exclusion {pattern!r} "
        f"for broad Docker context copy at {policy.dockerfile}:{copy_locations}"
        for pattern in missing
    )

    missing_reinclusions = sorted(policy.required_reinclusions - patterns)
    findings.extend(
        f"{policy.ignore_file}: missing required narrow reinclusion {pattern!r}"
        for pattern in missing_reinclusions
    )

    unexpected_reinclusions = sorted(
        pattern
        for pattern in patterns
        if pattern.startswith("!") and pattern not in policy.allowed_reinclusions
    )
    findings.extend(
        f"{policy.ignore_file}: unexpected reinclusion {pattern!r}; "
        "explicit policy review is required"
        for pattern in unexpected_reinclusions
    )

    return findings


def scan_repository(*, repo_root: Path = REPO_ROOT) -> list[str]:
    findings: list[str] = []
    for policy in POLICIES:
        findings.extend(policy_violations(policy, repo_root=repo_root))
    return findings


def main() -> int:
    findings = scan_repository()
    if findings:
        print("Docker build-context secret boundary violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("Docker build-context secret boundary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
