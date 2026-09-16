"""Bounded virtual studio for unattended, model-assisted repository work.

The studio intentionally models 1,000 specialist roles without starting 1,000
uncontrolled processes. A deterministic cohort is selected for each run. Model
output is always advisory until it passes deterministic proposal policy and the
repository's ordinary CI/review gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

BOT_COUNT = 1_000
MAX_ACTIVE_COHORT = 64
MAX_PROPOSAL_FILES = 8
MAX_FILE_BYTES = 80_000
MAX_BUNDLE_BYTES = 240_000

DOMAINS = (
    "gameplay-systems",
    "game-ai",
    "world-generation",
    "narrative",
    "simulation",
    "physics",
    "animation",
    "rendering",
    "audio",
    "multiplayer",
    "tools",
    "editor-ux",
    "content-pipeline",
    "testing",
    "performance",
    "reliability",
    "security",
    "data",
    "retrieval",
    "reasoning",
    "agent-runtime",
    "evaluation",
    "developer-experience",
    "research",
    "product-quality",
)

DISCIPLINES = (
    "architect",
    "implementer",
    "reviewer",
    "test-engineer",
    "adversarial-auditor",
    "performance-engineer",
    "integration-engineer",
    "researcher",
    "toolsmith",
    "quality-lead",
)

LANES = ("discover", "design", "build", "verify")

_BLOCKED_EXACT = {
    ".env",
    ".env.local",
    "pyproject.toml",
    "package-lock.json",
    "poetry.lock",
    "uv.lock",
}
_BLOCKED_PREFIXES = (
    ".git/",
    ".github/workflows/",
    ".github/actions/",
    "security/",
    "secrets/",
    "auth/",
)
_BLOCKED_FRAGMENTS = (
    "credential",
    "secret",
    "private_key",
    "private-key",
    "token-store",
)
_ALLOWED_PREFIXES = ("skeleton/", "tests/", "docs/")
_ALLOWED_ROOT_DOCS = {"README.md", "CHANGELOG.md", "BACKLOG.md"}


@dataclass(frozen=True, slots=True)
class StudioRole:
    bot_id: str
    domain: str
    discipline: str
    lane: str
    risk_budget: str
    token_budget: int


@dataclass(frozen=True, slots=True)
class ProposedFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    accepted: bool
    reasons: tuple[str, ...]
    fingerprint: str
    files: int
    bytes: int


@dataclass(frozen=True, slots=True)
class AuditEvent:
    timestamp: str
    run_id: str
    bot_id: str
    action: str
    status: str
    detail: str
    fingerprint: str


def build_registry() -> tuple[StudioRole, ...]:
    """Build the canonical 1,000-role studio manifest.

    25 domains x 10 disciplines x 4 execution lanes = exactly 1,000 roles.
    Roles are identities and responsibilities, not 1,000 simultaneous workers.
    """

    roles: list[StudioRole] = []
    ordinal = 1
    for domain in DOMAINS:
        for discipline in DISCIPLINES:
            for lane in LANES:
                risk_budget = "read-only" if lane in {"discover", "design"} else "proposal-only"
                token_budget = 12_000 if discipline in {"architect", "researcher"} else 8_000
                roles.append(
                    StudioRole(
                        bot_id=f"studio-{ordinal:04d}",
                        domain=domain,
                        discipline=discipline,
                        lane=lane,
                        risk_budget=risk_budget,
                        token_budget=token_budget,
                    )
                )
                ordinal += 1
    if len(roles) != BOT_COUNT:
        raise RuntimeError(f"studio manifest must contain {BOT_COUNT} roles")
    return tuple(roles)


def select_cohort(run_key: str, size: int = 32) -> tuple[StudioRole, ...]:
    """Select a deterministic, well-distributed bounded cohort for one run."""

    if not isinstance(run_key, str) or not run_key.strip():
        raise ValueError("run_key must be a non-empty string")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_ACTIVE_COHORT:
        raise ValueError(f"size must be between 1 and {MAX_ACTIVE_COHORT}")

    registry = build_registry()
    ranked = sorted(
        registry,
        key=lambda role: hashlib.sha256(f"{run_key}\x1f{role.bot_id}".encode()).digest(),
    )
    return tuple(ranked[:size])


def _canonical_repo_path(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        return None
    if raw.startswith("/") or raw.startswith("./"):
        return None
    pure = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in pure.parts):
        return None
    canonical = pure.as_posix()
    return canonical if canonical == raw else None


def _path_allowed(path: str) -> bool:
    lowered = path.lower()
    if path in _BLOCKED_EXACT:
        return False
    if any(lowered.startswith(prefix.lower()) for prefix in _BLOCKED_PREFIXES):
        return False
    if any(fragment in lowered for fragment in _BLOCKED_FRAGMENTS):
        return False
    return path in _ALLOWED_ROOT_DOCS or any(path.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def validate_proposal(files: Sequence[ProposedFile]) -> ProposalDecision:
    """Validate a model-produced file bundle before any filesystem mutation.

    This is deliberately stricter than normal human development. It forbids
    workflow/auth/security/dependency-control edits and caps both file count and
    bytes. The validator never executes model-produced commands.
    """

    reasons: list[str] = []
    normalized: list[tuple[str, bytes]] = []
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        reasons.append("proposal must be a sequence of files")
        files = ()
    if len(files) == 0:
        reasons.append("proposal is empty")
    if len(files) > MAX_PROPOSAL_FILES:
        reasons.append("too many files")

    seen: set[str] = set()
    for item in files:
        if not isinstance(item, ProposedFile):
            reasons.append("invalid proposal item")
            continue
        path = _canonical_repo_path(item.path)
        if path is None:
            reasons.append("invalid or non-canonical path")
            continue
        if path in seen:
            reasons.append(f"duplicate path: {path}")
            continue
        seen.add(path)
        if not _path_allowed(path):
            reasons.append(f"blocked path: {path}")
        if not isinstance(item.content, str):
            reasons.append(f"non-text content: {path}")
            continue
        payload = item.content.encode("utf-8")
        if len(payload) > MAX_FILE_BYTES:
            reasons.append(f"file too large: {path}")
        normalized.append((path, payload))

    total_bytes = sum(len(payload) for _, payload in normalized)
    if total_bytes > MAX_BUNDLE_BYTES:
        reasons.append("proposal bundle too large")

    fingerprint_payload = [
        f"{path}\x1f{hashlib.sha256(payload).hexdigest()}" for path, payload in sorted(normalized)
    ]
    fingerprint = hashlib.sha256("\x1e".join(fingerprint_payload).encode()).hexdigest()
    return ProposalDecision(
        accepted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        fingerprint=fingerprint,
        files=len(normalized),
        bytes=total_bytes,
    )


def parse_proposal_json(raw: str) -> tuple[ProposedFile, ...]:
    """Parse the only accepted model-to-builder interchange format."""

    if not isinstance(raw, str) or len(raw) > MAX_BUNDLE_BYTES * 2:
        raise ValueError("proposal payload is invalid or too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("proposal is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) != {"files"} or not isinstance(data["files"], list):
        raise ValueError("proposal must contain only a files list")

    result: list[ProposedFile] = []
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "content"}:
            raise ValueError("each proposal file must contain path and content only")
        if not isinstance(item["path"], str) or not isinstance(item["content"], str):
            raise ValueError("proposal path and content must be strings")
        result.append(ProposedFile(path=item["path"], content=item["content"]))
    return tuple(result)


def append_audit_event(path: Path, event: AuditEvent) -> None:
    """Append one JSONL event. Audit write failures are never ignored."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(event), sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()


def make_audit_event(
    *, run_id: str, bot_id: str, action: str, status: str, detail: str, fingerprint: str = ""
) -> AuditEvent:
    if status not in {"planned", "accepted", "rejected", "passed", "failed", "skipped"}:
        raise ValueError("invalid audit status")
    safe_detail = detail.replace("\r", " ").replace("\n", " ")[:2_000]
    return AuditEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_id=run_id[:200],
        bot_id=bot_id[:100],
        action=action[:200],
        status=status,
        detail=safe_detail,
        fingerprint=fingerprint[:128],
    )


def manifest_payload() -> dict[str, object]:
    roles = build_registry()
    return {
        "schema_version": 1,
        "bot_count": len(roles),
        "max_active_cohort": MAX_ACTIVE_COHORT,
        "domains": list(DOMAINS),
        "disciplines": list(DISCIPLINES),
        "lanes": list(LANES),
        "roles": [asdict(role) for role in roles],
    }


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded 1,000-role repository studio")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manifest")
    cohort = sub.add_parser("cohort")
    cohort.add_argument("--run-key", required=True)
    cohort.add_argument("--size", type=int, default=32)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "manifest":
        print(json.dumps(manifest_payload(), sort_keys=True))
        return 0
    if args.command == "cohort":
        selected = select_cohort(args.run_key, args.size)
        print(json.dumps([asdict(role) for role in selected], sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(_main())
