"""Reject direct GitHub Actions workflow inputs interpolated into shell commands.

Workflow-dispatch and reusable-workflow inputs are attacker- or caller-controlled
strings from the shell's perspective. They must cross the shell boundary through
an environment variable (or another non-code channel), never through direct
`${{ ... }}` interpolation inside a ``run:`` command.

This checker intentionally uses only the Python standard library so it can run in
an early CI phase without installing project dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
RUN_RE = re.compile(r"^(?P<indent>\s*)(?:-\s*)?run\s*:\s*(?P<value>.*)$")
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}")
UNTRUSTED_INPUT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:github\.event\.inputs|inputs)\s*(?:\.|\[)"
)
BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _run_fragments(lines: list[str]) -> Iterable[tuple[int, str]]:
    """Yield shell fragments and source line numbers from run steps."""
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


def _direct_input_expression(fragment: str) -> str | None:
    for expression in EXPRESSION_RE.finditer(fragment):
        body = expression.group("body")
        if UNTRUSTED_INPUT_RE.search(body):
            return body.strip()
    return None


def violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]

    findings: list[str] = []
    for line_number, fragment in _run_fragments(text.splitlines()):
        expression = _direct_input_expression(fragment)
        if expression is None:
            continue
        findings.append(
            f"{path.name}:{line_number}: direct workflow input interpolation in run shell is forbidden "
            f"({expression}); pass the input through env and quote the environment variable instead"
        )
    return findings


def main() -> int:
    workflows = workflow_files()
    if not workflows:
        print("No GitHub Actions workflows found.", file=sys.stderr)
        return 1

    findings: list[str] = []
    for path in workflows:
        findings.extend(violations(path))

    if findings:
        print("GitHub Actions workflow input shell-boundary violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(
        f"Workflow input security gate passed for {len(workflows)} workflow files: "
        "no direct inputs.* or github.event.inputs.* interpolation in run shells."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
