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
FLOW_STEP_RE = re.compile(r"^(?P<indent>\s*)-\s*\{")
FLOW_RUN_KEY_RE = re.compile(r"^(?:run|'run'|\"run\")\s*:")
# GitHub Actions supports YAML anchors and aliases. An alias used as the value
# of ``run`` hides the shell text from this lightweight scanner because resolving
# aliases requires parsing the whole YAML document. Reject such shell aliases
# fail-closed instead of treating the opaque alias name as trusted shell text.
RUN_ALIAS_RE = re.compile(r"^\*[^\s#]+(?:\s+#.*)?$")
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
# YAML block scalars may carry node properties such as ``&anchor`` or ``!tag``
# before the scalar indicator. They may also combine a chomping indicator (+/-)
# and an indentation indicator (1-9) in either order: |, |-, |2, |2-, |-2,
# >+2, and so on. A trailing YAML comment is legal after whitespace. Recognize
# this full family so anchors, tags, and alternate headers cannot hide a run body.
BLOCK_SCALAR_RE = re.compile(
    r"^(?:(?:[!&][^\s#]+)\s+)*"
    r"[|>](?:(?:[+-][1-9]?)|(?:[1-9][+-]?))?(?:\s+#.*)?$"
)


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _flow_mapping_depth(fragment: str) -> int:
    """Return brace depth for a YAML flow mapping, ignoring quoted braces."""
    start = fragment.find("{")
    if start < 0:
        return 0

    depth = 0
    in_single = False
    in_double = False
    escaped = False
    index = start
    while index < len(fragment):
        char = fragment[index]
        if in_single:
            if char == "'" and index + 1 < len(fragment) and fragment[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_double = False
            index += 1
            continue

        if char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return depth


def _flow_mapping_entries(fragment: str) -> list[str]:
    """Split the outer YAML flow mapping into top-level entries only."""
    start = fragment.find("{")
    if start < 0:
        return []

    entries: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    escaped = False
    index = start

    while index < len(fragment):
        char = fragment[index]
        if in_single:
            if depth >= 1:
                current.append(char)
            if char == "'" and index + 1 < len(fragment) and fragment[index + 1] == "'":
                if depth >= 1:
                    current.append(fragment[index + 1])
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            if depth >= 1:
                current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_double = False
            index += 1
            continue

        if char == "'":
            in_single = True
            if depth >= 1:
                current.append(char)
        elif char == '"':
            in_double = True
            if depth >= 1:
                current.append(char)
        elif char == "{":
            depth += 1
            if depth > 1:
                current.append(char)
        elif char == "}":
            if depth == 1:
                entry = "".join(current).strip()
                if entry:
                    entries.append(entry)
                current = []
                depth -= 1
                break
            if depth > 1:
                depth -= 1
                current.append(char)
        elif char == "," and depth == 1:
            entry = "".join(current).strip()
            if entry:
                entries.append(entry)
            current = []
        elif depth >= 1:
            current.append(char)
        index += 1

    if current and depth >= 1:
        entry = "".join(current).strip()
        if entry:
            entries.append(entry)
    return entries


def _flow_style_steps(lines: list[str]) -> Iterable[tuple[int, str]]:
    """Yield complete flow-style step mappings, including multiline forms."""
    index = 0
    while index < len(lines):
        line = lines[index]
        match = FLOW_STEP_RE.match(line)
        if not match:
            index += 1
            continue

        start_line = index + 1
        base_indent = len(match.group("indent"))
        block_lines = [line]
        while _flow_mapping_depth("\n".join(block_lines)) > 0 and index + 1 < len(lines):
            next_line = lines[index + 1]
            if next_line.strip() and _indent_width(next_line) < base_indent:
                break
            index += 1
            block_lines.append(lines[index])
        yield start_line, "\n".join(block_lines)
        index += 1


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
    lines = text.splitlines()

    for line_number, fragment in _flow_style_steps(lines):
        if any(FLOW_RUN_KEY_RE.match(entry.strip()) for entry in _flow_mapping_entries(fragment)):
            findings.append(
                f"{path.name}:{line_number}: flow-style run step is forbidden because the security gate "
                "cannot safely audit shell boundaries in compact YAML mappings; use a block-style run step"
            )

    for line_number, fragment in _run_fragments(lines):
        if RUN_ALIAS_RE.fullmatch(fragment.strip()):
            findings.append(
                f"{path.name}:{line_number}: aliased run shell is forbidden because the security gate "
                "cannot verify the referenced shell text; inline the command or use a reusable action/workflow"
            )
            continue

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
