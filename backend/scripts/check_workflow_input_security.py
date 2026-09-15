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
# YAML permits plain, single-quoted, and double-quoted mapping keys. Treat all
# legal spellings of the GitHub Actions ``run`` key as shell boundaries so a
# quoted key cannot bypass the interpolation gate.
RUN_RE = re.compile(
    r"^(?P<indent>\s*)(?:-\s*)?(?:run|'run'|\"run\")\s*:\s*(?P<value>.*)$"
)
# A GitHub expression embedded in a YAML block scalar may span physical lines.
# DOTALL ensures the security gate inspects the expression after the full run
# block has been reconstructed instead of only matching single-line forms.
EXPRESSION_RE = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)
# Match the input contexts as expression tokens, not only property access.
# Whole-object transforms such as toJSON(inputs) remain attacker-controlled and
# must not be interpolated directly into a shell command either.
UNTRUSTED_INPUT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:github\.event\.inputs|inputs)(?![A-Za-z0-9_])"
)
# YAML block scalars may combine a chomping indicator (+/-) and an indentation
# indicator (1-9) in either order: |, |-, |2, |2-, |-2, >+2, and so on.
# A trailing YAML comment is also legal after whitespace. Recognize the full
# family so alternate scalar headers cannot hide the shell body from the gate.
BLOCK_SCALAR_RE = re.compile(
    r"^[|>](?:(?:[+-][1-9]?)|(?:[1-9][+-]?))?(?:\s+#.*)?$"
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _run_fragments(lines: list[str]) -> Iterable[tuple[int, str]]:
    """Yield complete shell fragments and source line numbers from run steps."""
    index = 0
    while index < len(lines):
        line = lines[index]
        match = RUN_RE.match(line)
        if not match:
            index += 1
            continue

        value = match.group("value").strip()
        line_number = index + 1
        if not BLOCK_SCALAR_RE.fullmatch(value):
            yield line_number, value
            index += 1
            continue

        base_indent = len(match.group("indent"))
        index += 1
        block_lines: list[str] = []
        first_content_line: int | None = None
        while index < len(lines):
            child = lines[index]
            if child.strip() and _indent_width(child) <= base_indent:
                break
            if child.strip() and first_content_line is None:
                first_content_line = index + 1
            block_lines.append(child)
            index += 1

        if first_content_line is not None:
            # Keep the complete block together. YAML folded scalars can turn
            # physical newlines into spaces, and GitHub expressions may contain
            # whitespace, so line-by-line scanning would permit split-expression
            # bypasses such as `${{` / `inputs.payload` / `}}` on separate lines.
            yield first_content_line, "\n".join(block_lines)


def _without_expression_string_literals(body: str) -> str:
    """Blank GitHub-expression single-quoted strings while preserving tokens.

    GitHub expressions use single-quoted string literals and escape a literal
    quote by doubling it. Ignoring literal contents prevents harmless text such
    as ``'inputs.payload'`` from being mistaken for an input-context reference.
    """
    output: list[str] = []
    index = 0
    in_string = False

    while index < len(body):
        char = body[index]
        if char == "'":
            if in_string and index + 1 < len(body) and body[index + 1] == "'":
                output.extend((" ", " "))
                index += 2
                continue
            in_string = not in_string
            output.append(" ")
        elif in_string:
            output.append(" ")
        else:
            output.append(char)
        index += 1

    return "".join(output)


def _direct_input_expression(fragment: str) -> str | None:
    for expression in EXPRESSION_RE.finditer(fragment):
        body = expression.group("body")
        searchable = _without_expression_string_literals(body)
        if UNTRUSTED_INPUT_RE.search(searchable):
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
        "no direct inputs or github.event.inputs interpolation in run shells."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
