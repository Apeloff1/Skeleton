"""Static GitHub Actions policy gate.

The checker is dependency-free so it can run in the earliest CI phase. It
requires immutable action references, explicit workflow permissions, rejects
high-risk event/permission patterns, and prevents direct interpolation of
attacker-controlled GitHub event fields into shell ``run`` commands.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
USES_RE = re.compile(r"^\s*(?:-\s*)?(?:\{\s*)?uses\s*:\s*[\"']?([^\"'\s,}#]+)")
RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?run\s*:\s*(?P<value>.*)$")
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}")
BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}

# These fields can be controlled by pull-request authors, issue/comment authors,
# or commit authors. They must cross the shell boundary through env/input data,
# never by direct expression interpolation inside a run command.
UNTRUSTED_RUN_CONTEXTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pull request title/body", re.compile(r"\bgithub\.event\.pull_request\.(?:title|body)\b")),
    ("pull request head ref/label", re.compile(r"\bgithub\.event\.pull_request\.head\.(?:ref|label)\b")),
    ("issue title/body", re.compile(r"\bgithub\.event\.issue\.(?:title|body)\b")),
    ("issue comment body", re.compile(r"\bgithub\.event\.comment\.body\b")),
    ("review body", re.compile(r"\bgithub\.event\.(?:review|review_comment)\.body\b")),
    ("head commit message", re.compile(r"\bgithub\.event\.head_commit\.message\b")),
    ("head ref", re.compile(r"\bgithub\.head_ref\b")),
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _is_local(reference: str) -> bool:
    return reference.startswith("./")


def _container_violation(reference: str) -> str | None:
    if not reference.startswith("docker://"):
        return None
    target = reference.removeprefix("docker://")
    if "@sha256:" not in target:
        return "container action must be pinned to an immutable sha256 digest"
    image, digest = target.rsplit("@sha256:", 1)
    if not image or not SHA256_RE.fullmatch(digest):
        return "container action has an invalid sha256 digest pin"
    return None


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _run_fragments(lines: list[str]) -> Iterable[tuple[int, str]]:
    """Yield shell source fragments with their workflow line numbers."""
    index = 0
    while index < len(lines):
        line = lines[index]
        match = RUN_RE.match(line)
        if not match:
            index += 1
            continue

        value = match.group("value").strip()
        line_number = index + 1
        if value not in BLOCK_SCALARS:
            yield line_number, value
            index += 1
            continue

        base_indent = len(match.group("indent"))
        index += 1
        while index < len(lines):
            child = lines[index]
            if child.strip() and _indent_width(child) <= base_indent:
                break
            if child.strip():
                yield index + 1, child.strip()
            index += 1


def _untrusted_expression(fragment: str) -> str | None:
    for expression in EXPRESSION_RE.finditer(fragment):
        body = expression.group("body")
        for label, pattern in UNTRUSTED_RUN_CONTEXTS:
            if pattern.search(body):
                return label
    return None


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings: list[str] = []
    lines = text.splitlines()
    has_top_level_permissions = False

    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if line == stripped and stripped.startswith("permissions:"):
            has_top_level_permissions = True
            if stripped in {"permissions: write-all", "permissions: write"}:
                findings.append(f"{path.name}:{number}: workflow-wide write permissions are forbidden")

        if re.match(r"^\s*pull_request_target\s*:", line):
            findings.append(f"{path.name}:{number}: pull_request_target is forbidden")

        if re.match(r"^\s*permissions\s*:\s*write-all\s*$", line):
            findings.append(f"{path.name}:{number}: write-all permissions are forbidden")

        match = USES_RE.match(line)
        if not match:
            continue
        reference = match.group(1).strip("\"'")
        if _is_local(reference):
            continue
        if reference.startswith("docker://"):
            container_violation = _container_violation(reference)
            if container_violation:
                findings.append(f"{path.name}:{number}: {container_violation}: {reference}")
            continue
        if "@" not in reference:
            findings.append(f"{path.name}:{number}: action reference must be pinned to an immutable commit SHA: {reference}")
            continue
        _action, revision = reference.rsplit("@", 1)
        if not SHA40_RE.fullmatch(revision):
            findings.append(f"{path.name}:{number}: action reference is not pinned to a 40-character commit SHA: {reference}")

    for number, fragment in _run_fragments(lines):
        label = _untrusted_expression(fragment)
        if label:
            findings.append(
                f"{path.name}:{number}: direct {label} interpolation in run shell is forbidden; pass it through env instead"
            )

    if not has_top_level_permissions:
        findings.append(f"{path.name}: missing explicit top-level permissions block")
    return findings


def main() -> int:
    findings: list[str] = []
    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1
    for path in workflows:
        findings.extend(violations(path))
    if findings:
        print("GitHub Actions workflow security violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"Workflow security gate passed for {len(workflows)} workflow files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
