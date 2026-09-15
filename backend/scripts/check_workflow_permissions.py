"""Enforce least-privilege GitHub Actions token permissions.

Every workflow must explicitly constrain ``GITHUB_TOKEN`` at workflow scope.
Write permissions belong only on the individual job that performs the mutation;
workflow-wide writes make unrelated jobs unnecessarily privileged.  Broad
``read-all``/``write-all`` shorthands are also rejected.

This gate intentionally uses only the Python standard library so it can execute
before project dependencies are installed.  It parses only the small permissions
surface we permit and fails closed on opaque YAML forms rather than attempting to
be a general YAML parser.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

PERMISSIONS_KEY_RE = re.compile(
    r"^(?P<indent> *)(?:permissions|'permissions'|\"permissions\")\s*:\s*(?P<value>.*)$"
)
SCOPE_RE = re.compile(
    r"^(?P<indent> +)(?P<scope>[A-Za-z-]+)\s*:\s*(?P<value>read|write|none)\s*(?:#.*)?$",
    re.IGNORECASE,
)
BROAD_PERMISSION_RE = re.compile(
    r"^(?P<indent> *)(?:permissions|'permissions'|\"permissions\")\s*:\s*"
    r"(?P<quote>['\"]?)(?P<value>read-all|write-all)(?P=quote)\s*(?:#.*)?$",
    re.IGNORECASE,
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _top_level_permission_block(lines: list[str]) -> tuple[int, str, list[str]] | None:
    matches: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = PERMISSIONS_KEY_RE.match(line)
        if match and len(match.group("indent")) == 0:
            matches.append((index, match))

    if len(matches) != 1:
        return None

    index, match = matches[0]
    children: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        line = lines[cursor]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            children.append(line)
            cursor += 1
            continue
        if _indent(line) == 0:
            break
        children.append(line)
        cursor += 1
    return index + 1, match.group("value").strip(), children


def violations_from_text(name: str, text: str) -> list[str]:
    lines = text.splitlines()
    findings: list[str] = []

    top_level_matches = [
        (index + 1, match)
        for index, line in enumerate(lines)
        if (match := PERMISSIONS_KEY_RE.match(line)) is not None
        and len(match.group("indent")) == 0
    ]
    if not top_level_matches:
        findings.append(
            f"{name}: missing top-level permissions declaration; use permissions: {{}} "
            "or explicit read-only scopes"
        )
    elif len(top_level_matches) > 1:
        findings.append(
            f"{name}: multiple top-level permissions declarations are forbidden"
        )
    else:
        block = _top_level_permission_block(lines)
        assert block is not None
        line_number, value, children = block
        normalized = value.split("#", 1)[0].strip().lower()
        if normalized:
            if normalized in {"read-all", "write-all"}:
                findings.append(
                    f"{name}:{line_number}: broad top-level permissions shorthand "
                    f"'{normalized}' is forbidden"
                )
            elif normalized != "{}":
                findings.append(
                    f"{name}:{line_number}: opaque/inline top-level permissions are forbidden; "
                    "use permissions: {} or a block mapping of explicit read-only scopes"
                )
        else:
            for offset, child in enumerate(children, start=line_number + 1):
                stripped = child.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                scope = SCOPE_RE.match(child)
                if scope is None:
                    findings.append(
                        f"{name}:{offset}: unsupported top-level permissions syntax; "
                        "use explicit scope: read/none entries"
                    )
                    continue
                if scope.group("value").lower() == "write":
                    findings.append(
                        f"{name}:{offset}: workflow-wide '{scope.group('scope')}: write' is forbidden; "
                        "grant writes only to the mutating job"
                    )

    for index, line in enumerate(lines, start=1):
        broad = BROAD_PERMISSION_RE.match(line)
        if broad:
            findings.append(
                f"{name}:{index}: broad permissions shorthand '{broad.group('value').lower()}' "
                "is forbidden; enumerate only the scopes the job needs"
            )

    return sorted(set(findings))


def violations(path: Path) -> list[str]:
    if path.is_symlink():
        return [f"{path.name}: workflow files must not be symlinks"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path.name}: cannot inspect workflow permissions: {type(exc).__name__}"]
    return violations_from_text(path.name, text)


def main() -> int:
    if WORKFLOW_DIR.is_symlink():
        print("GitHub Actions workflow directory must not be a symlink.", file=sys.stderr)
        return 1

    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1

    findings: list[str] = []
    for path in workflows:
        findings.extend(violations(path))

    if findings:
        print("GitHub Actions token-permission violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Workflow permission gate passed for {len(workflows)} workflow files: "
        "every workflow has an explicit deny/read-only ceiling and no broad permission shorthand."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
