"""Enforce Docker build-context and build-layer secret boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SECRET_EXCLUSIONS = frozenset({
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
})
REQUIRED_REINCLUSIONS = frozenset({"!.env.example"})
ALLOWED_REINCLUSIONS = REQUIRED_REINCLUSIONS
ROOT_REQUIRED_SECRET_EXCLUSIONS = REQUIRED_SECRET_EXCLUSIONS | frozenset({
    "**/.env",
    "**/.env.*",
})
ROOT_REQUIRED_REINCLUSIONS = REQUIRED_REINCLUSIONS | frozenset({"!**/.env.example"})
ROOT_ALLOWED_REINCLUSIONS = ROOT_REQUIRED_REINCLUSIONS
BROAD_COPY_RE = re.compile(
    r"^\s*(?:COPY|ADD)\s+(?:--\S+\s+)*\.\s+\.\s*(?:#.*)?$",
    re.IGNORECASE,
)
SECRET_DIRECTIVE_NAME_RE = re.compile(
    r"(?:^|_)(?:SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE_KEY|CREDENTIALS?|API_KEY|ACCESS_KEY|CLIENT_SECRET)(?:_|$)",
    re.IGNORECASE,
)
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PARSER_ESCAPE_RE = re.compile(
    r"^#\s*escape\s*=\s*(?P<escape>[\\`])\s*$",
    re.IGNORECASE,
)
DEPLOYABLE_DOCKERFILES = (
    Path("Dockerfile"),
    Path("backend/Dockerfile"),
    Path("frontend/Dockerfile"),
)


@dataclass(frozen=True)
class DockerContextPolicy:
    dockerfile: Path
    ignore_file: Path
    required_exclusions: frozenset[str] = REQUIRED_SECRET_EXCLUSIONS
    required_reinclusions: frozenset[str] = REQUIRED_REINCLUSIONS
    allowed_reinclusions: frozenset[str] = ALLOWED_REINCLUSIONS
    require_broad_copy: bool = True
    always_require_ignore: bool = False


POLICIES = (
    DockerContextPolicy(Path("frontend/Dockerfile"), Path("frontend/.dockerignore")),
    DockerContextPolicy(
        Path("backend/Dockerfile"),
        Path(".dockerignore"),
        required_exclusions=ROOT_REQUIRED_SECRET_EXCLUSIONS,
        required_reinclusions=ROOT_REQUIRED_REINCLUSIONS,
        allowed_reinclusions=ROOT_ALLOWED_REINCLUSIONS,
        require_broad_copy=False,
        always_require_ignore=True,
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
    dockerfile = repo_root / policy.dockerfile
    ignore_file = repo_root / policy.ignore_file
    docker_text, errors = _safe_read(dockerfile, label=str(policy.dockerfile))
    if errors:
        return errors
    assert docker_text is not None
    broad = [
        number
        for number, line in enumerate(docker_text.splitlines(), 1)
        if BROAD_COPY_RE.match(line)
    ]
    if policy.require_broad_copy and not broad:
        return [
            f"{policy.dockerfile}: expected broad Docker context copy is absent; "
            "review this guard with the Dockerfile change"
        ]
    if not broad and not policy.always_require_ignore:
        return []

    ignore_text, errors = _safe_read(ignore_file, label=str(policy.ignore_file))
    if errors:
        return errors
    assert ignore_text is not None
    patterns = _active_ignore_patterns(ignore_text)
    locations = ",".join(map(str, broad)) if broad else "context"
    findings = [
        f"{policy.ignore_file}: missing required secret exclusion {pattern!r} for "
        f"Docker context used by {policy.dockerfile}:{locations}"
        for pattern in sorted(policy.required_exclusions - patterns)
    ]
    findings += [
        f"{policy.ignore_file}: missing required narrow reinclusion {pattern!r}"
        for pattern in sorted(policy.required_reinclusions - patterns)
    ]
    findings += [
        f"{policy.ignore_file}: unexpected reinclusion {pattern!r}; explicit policy review is required"
        for pattern in sorted(
            pattern
            for pattern in patterns
            if pattern.startswith("!") and pattern not in policy.allowed_reinclusions
        )
    ]
    return findings


def _docker_escape_character(text: str) -> str:
    """Resolve Docker's optional leading ``# escape=`` parser directive."""
    escape = "\\"
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            break
        match = PARSER_ESCAPE_RE.fullmatch(stripped)
        if match:
            escape = match.group("escape")
    return escape


def _logical_instructions(text: str):
    """Yield ``(start_line, instruction)`` with Docker continuations joined."""
    escape = _docker_escape_character(text)
    parts: list[str] = []
    start_line = 0
    for number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not parts:
            start_line = number
        continued = stripped.endswith(escape)
        piece = stripped[:-1].rstrip() if continued else stripped
        parts.append(piece)
        if not continued:
            yield start_line, " ".join(parts)
            parts = []
    if parts:
        yield start_line, " ".join(parts)


def _secret_directive_names(instruction: str) -> tuple[list[str], str | None]:
    operation, separator, payload = instruction.partition(" ")
    operation = operation.upper()
    if not separator or operation not in {"ARG", "ENV"}:
        return [], None
    payload = payload.strip()
    if not payload:
        return [], f"malformed {operation} instruction"

    if operation == "ARG":
        name = payload.split("=", 1)[0].strip()
        if not ENV_NAME_RE.fullmatch(name):
            return [], "malformed ARG instruction"
        return [name], None

    try:
        tokens = shlex.split(payload, comments=True, posix=True)
    except ValueError:
        return [], "malformed ENV instruction"
    if not tokens:
        return [], "malformed ENV instruction"

    assignment_tokens = [token for token in tokens if "=" in token]
    if assignment_tokens:
        names = [token.split("=", 1)[0] for token in assignment_tokens]
    else:
        names = [tokens[0]]
    if any(not ENV_NAME_RE.fullmatch(name) for name in names):
        return [], "malformed ENV instruction"
    return names, None


def dockerfile_secret_directive_violations(
    dockerfile: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    """Reject secret-bearing ARG/ENV names in deployable Dockerfiles.

    Build arguments and Dockerfile ENV instructions are not secret channels:
    values can persist in image metadata, build history, caches, or layers.
    Runtime secrets must enter through the deployment/runtime secret mechanism;
    build-time secrets must use a dedicated BuildKit secret mount instead.
    """
    text, errors = _safe_read(repo_root / dockerfile, label=str(dockerfile))
    if errors:
        return errors
    assert text is not None

    findings: list[str] = []
    for line_number, instruction in _logical_instructions(text):
        names, error = _secret_directive_names(instruction)
        if error is not None:
            findings.append(f"{dockerfile}:{line_number}: {error}")
            continue
        for name in names:
            if SECRET_DIRECTIVE_NAME_RE.search(name):
                findings.append(
                    f"{dockerfile}:{line_number}: secret-bearing Docker ARG/ENV name {name!r} is forbidden; "
                    "use runtime secret injection or a BuildKit secret mount"
                )
    return findings


def scan_repository(*, repo_root: Path = REPO_ROOT) -> list[str]:
    findings: list[str] = []
    for policy in POLICIES:
        findings.extend(policy_violations(policy, repo_root=repo_root))
    for dockerfile in DEPLOYABLE_DOCKERFILES:
        findings.extend(
            dockerfile_secret_directive_violations(dockerfile, repo_root=repo_root)
        )
    return findings


def main() -> int:
    findings = scan_repository()
    if findings:
        print("Docker secret boundary violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Docker build-context and build-layer secret boundary passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
