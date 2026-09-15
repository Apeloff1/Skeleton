"""Static GitHub Actions policy gate.

The checker is dependency-free so it can run in the earliest CI phase. It
requires immutable action references, explicit workflow permissions, hardened
checkout credential handling, rejects workflow-wide token elevation and
high-risk event/permission patterns, and prevents direct interpolation of
attacker-controlled GitHub event fields into shell ``run`` commands.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

if __package__:
    from .check_workflow_input_security import (
        _run_fragments as hardened_run_fragments,
        violations as input_boundary_violations,
    )
else:
    from check_workflow_input_security import (
        _run_fragments as hardened_run_fragments,
        violations as input_boundary_violations,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
USES_RE = re.compile(
    r"^\s*(?:-\s*)?(?:\{\s*)?(?:uses|'uses'|\"uses\")\s*:\s*[\"']?([^\"'\s,}#]+)"
)
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
PERSIST_FALSE_RE = re.compile(
    r"(?:persist-credentials|'persist-credentials'|\"persist-credentials\")\s*:\s*"
    r"(?:false|['\"]false['\"])(?=\s*[,}#]|\s*$)",
    re.IGNORECASE,
)
PERMISSION_ENTRY_RE = re.compile(
    r"^\s+['\"]?(?P<scope>[A-Za-z0-9_-]+)['\"]?\s*:\s*"
    r"(?P<value>read|write|none)\s*(?:#.*)?$",
    re.IGNORECASE,
)
PULL_REQUEST_TARGET_RE = re.compile(
    r"^\s*(?:pull_request_target|'pull_request_target'|\"pull_request_target\")\s*:"
)
CHECKOUT_ACTION = "actions/checkout@"

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


def _checkout_credentials_disabled(lines: list[str], uses_index: int) -> bool:
    """Return whether a checkout step explicitly disables credential persistence."""
    base_indent = _indent_width(lines[uses_index])
    index = uses_index + 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped:
            indent = _indent_width(line)
            if indent < base_indent or (indent == base_indent and stripped.startswith("- ")):
                break
            if PERSIST_FALSE_RE.search(line):
                return True
        index += 1
    return False


def _top_level_permission_violations(
    lines: list[str], path_name: str
) -> tuple[bool, list[str]]:
    """Require explicit read/none workflow defaults and job-local write elevation.

    GitHub applies workflow-level permissions to every job unless overridden.
    A global ``*: write`` therefore widens the token for unrelated jobs. This
    gate requires all write scopes to be granted inside the specific job that
    needs them. ``read-all`` is rejected for the same least-privilege reason:
    workflows should name the read scopes they actually consume (or use ``{}``).
    """
    findings: list[str] = []
    has_top_level = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if line != stripped or not stripped.startswith("permissions:"):
            continue

        has_top_level = True
        number = index + 1
        declaration = stripped.split("#", 1)[0].strip()
        inline = declaration.partition(":")[2].strip().lower()

        if inline in {"write-all", "write"}:
            findings.append(
                f"{path_name}:{number}: workflow-wide write permissions are forbidden; grant write scopes only to the job that needs them"
            )
            continue
        if inline == "read-all":
            findings.append(
                f"{path_name}:{number}: workflow-wide read-all is forbidden; declare only required read scopes"
            )
            continue
        if inline:
            # ``permissions: {}`` is an intentional no-permissions default.
            if inline != "{}":
                findings.append(
                    f"{path_name}:{number}: unsupported top-level permissions scalar; use a scoped mapping or {{}}"
                )
            continue

        child_index = index + 1
        while child_index < len(lines):
            child = lines[child_index]
            if child.strip() and _indent_width(child) == 0:
                break
            match = PERMISSION_ENTRY_RE.match(child)
            if match and match.group("value").lower() == "write":
                findings.append(
                    f"{path_name}:{child_index + 1}: workflow-wide {match.group('scope')}: write is forbidden; move elevation to the specific job"
                )
            child_index += 1

    return has_top_level, findings


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
    # Compose the dedicated workflow-input boundary checker into the canonical
    # workflow security gate. This keeps multiline expressions, quoted run keys,
    # block scalar variants, YAML anchors/tags, flow-style run mappings, and run
    # aliases fail-closed in the fast Backend Quality gate.
    findings.extend(input_boundary_violations(path))

    lines = text.splitlines()
    has_top_level_permissions, permission_findings = _top_level_permission_violations(
        lines, path.name
    )
    findings.extend(permission_findings)

    for index, line in enumerate(lines):
        number = index + 1

        if PULL_REQUEST_TARGET_RE.match(line):
            findings.append(f"{path.name}:{number}: pull_request_target is forbidden")

        if re.match(r"^\s*permissions\s*:\s*write-all\s*$", line):
            findings.append(f"{path.name}:{number}: write-all permissions are forbidden")

        match = USES_RE.match(line)
        if not match:
            continue
        reference = match.group(1).strip("\"'")

        if reference.startswith(CHECKOUT_ACTION) and not _checkout_credentials_disabled(lines, index):
            findings.append(
                f"{path.name}:{number}: actions/checkout must set persist-credentials: false"
            )

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

    # Reuse the hardened run parser from the input-boundary gate for every
    # attacker-controlled event context too. This prevents quoted run keys,
    # anchored/tagged block scalars, alternate scalar headers, and folded
    # multiline expressions from creating a second parser bypass surface.
    for number, fragment in hardened_run_fragments(lines):
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
