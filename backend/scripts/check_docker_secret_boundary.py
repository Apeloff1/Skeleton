"""Enforce secret exclusions for Docker contexts that copy the repository broadly.

A Dockerfile that uses ``COPY . .`` sends the build context to the daemon before
any image-layer policy can help.  This gate keeps the adjacent ``.dockerignore``
as an explicit, regression-tested security boundary for credential-shaped local
files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]

# Keep this list intentionally small and high-confidence.  These entries match
# local credential/key material that should never enter a frontend build context.
REQUIRED_SECRET_EXCLUSIONS = frozenset(
    {
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "credentials*.json",
        "service-account*.json",
    }
)

# Match shell-form broad copies while allowing ordinary COPY options such as
# --chown. JSON-array COPY is intentionally not considered broad here because the
# canonical Dockerfile does not use it and guessing Docker parsing semantics would
# make the gate less deterministic.
BROAD_COPY_RE = re.compile(
    r"^\s*(?:COPY|ADD)\s+(?:--\S+\s+)*\.\s+\.\s*(?:#.*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DockerContextPolicy:
    dockerfile: Path
    ignore_file: Path
    required_exclusions: frozenset[str] = REQUIRED_SECRET_EXCLUSIONS


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
    if not broad_copy_lines:
        return []

    ignore_text, errors = _safe_read(ignore_file, label=str(policy.ignore_file))
    if errors:
        return errors
    assert ignore_text is not None

    patterns = _active_ignore_patterns(ignore_text)
    missing = sorted(policy.required_exclusions - patterns)
    if not missing:
        return []

    copy_locations = ",".join(str(number) for number in broad_copy_lines)
    return [
        f"{policy.ignore_file}: missing required secret exclusion {pattern!r} "
        f"for broad Docker context copy at {policy.dockerfile}:{copy_locations}"
        for pattern in missing
    ]


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
