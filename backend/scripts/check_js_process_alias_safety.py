"""Reject JavaScript/TypeScript child_process namespace aliases that hide shell execution.

The primary SAST gate catches direct ``child_process.exec`` calls and destructured
``exec``/``execSync`` imports. This companion gate closes namespace-alias bypasses
while keeping false positives low by distinguishing executable code from comments
and string/template literal data. Expressions inside template literals remain code.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    "coverage",
}
JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
NAMESPACE_IMPORT_RE = re.compile(
    rf"^[ \t]*import\s*\*\s*as\s*(?P<esm>{IDENTIFIER})\s*from\s*['\"](?:node:)?child_process['\"]"
    rf"|^[ \t]*(?:const|let|var)\s+(?P<cjs>{IDENTIFIER})\s*=\s*require\s*\(\s*['\"](?:node:)?child_process['\"]\s*\)",
    re.MULTILINE,
)


def javascript_files() -> Iterable[Path]:
    if not FRONTEND_ROOT.exists():
        return
    for path in FRONTEND_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in JS_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def display_path(path: Path) -> Path:
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _mask_comments(text: str) -> str:
    """Mask comments while preserving strings, offsets, and newlines."""
    chars = list(text)
    out = list(text)
    state = "code"
    quote = ""
    escaped = False
    template_expr_depths: list[int] = []
    i = 0

    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""

        if state == "line-comment":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue

        if state == "block-comment":
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                state = "code"
                i += 2
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue

        if state in {"single", "double"}:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif (state == "single" and ch == "'") or (state == "double" and ch == '"'):
                state = "code"
            i += 1
            continue

        if state == "template":
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if ch == "`":
                state = "code"
                i += 1
                continue
            if ch == "$" and nxt == "{":
                template_expr_depths.append(1)
                state = "code"
                i += 2
                continue
            i += 1
            continue

        # Executable code, including the body of ${...} template expressions.
        if ch == "/" and nxt == "/":
            out[i] = out[i + 1] = " "
            state = "line-comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            out[i] = out[i + 1] = " "
            state = "block-comment"
            i += 2
            continue
        if ch == "'":
            state = "single"
            escaped = False
            i += 1
            continue
        if ch == '"':
            state = "double"
            escaped = False
            i += 1
            continue
        if ch == "`":
            state = "template"
            escaped = False
            i += 1
            continue
        if template_expr_depths:
            if ch == "{":
                template_expr_depths[-1] += 1
            elif ch == "}":
                template_expr_depths[-1] -= 1
                if template_expr_depths[-1] == 0:
                    template_expr_depths.pop()
                    state = "template"
        i += 1

    return "".join(out)


def _code_positions(text: str) -> list[bool]:
    """Mark positions that belong to executable JS/TS code.

    Literal template text is non-code, but `${...}` bodies are executable and
    therefore remain marked as code, including nested template expressions.
    """
    positions = [False] * len(text)
    state = "code"
    escaped = False
    template_expr_depths: list[int] = []
    i = 0

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "line-comment":
            if ch == "\n":
                state = "code"
            i += 1
            continue

        if state == "block-comment":
            if ch == "*" and nxt == "/":
                i += 2
                state = "code"
            else:
                i += 1
            continue

        if state in {"single", "double"}:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif (state == "single" and ch == "'") or (state == "double" and ch == '"'):
                state = "code"
            i += 1
            continue

        if state == "template":
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if ch == "`":
                state = "code"
                i += 1
                continue
            if ch == "$" and nxt == "{":
                template_expr_depths.append(1)
                state = "code"
                i += 2
                continue
            i += 1
            continue

        # Executable code.
        positions[i] = True
        if ch == "/" and nxt == "/":
            positions[i] = False
            if i + 1 < len(text):
                positions[i + 1] = False
            state = "line-comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            positions[i] = False
            if i + 1 < len(text):
                positions[i + 1] = False
            state = "block-comment"
            i += 2
            continue
        if ch == "'":
            positions[i] = False
            state = "single"
            escaped = False
            i += 1
            continue
        if ch == '"':
            positions[i] = False
            state = "double"
            escaped = False
            i += 1
            continue
        if ch == "`":
            positions[i] = False
            state = "template"
            escaped = False
            i += 1
            continue
        if template_expr_depths:
            if ch == "{":
                template_expr_depths[-1] += 1
            elif ch == "}":
                template_expr_depths[-1] -= 1
                if template_expr_depths[-1] == 0:
                    template_expr_depths.pop()
                    state = "template"
        i += 1

    return positions


def _starts_in_code(code_positions: list[bool], start: int) -> bool:
    return 0 <= start < len(code_positions) and code_positions[start]


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}: read failure: {exc}"]

    scan_text = _mask_comments(text)
    code_positions = _code_positions(text)

    aliases: set[str] = set()
    for match in NAMESPACE_IMPORT_RE.finditer(scan_text):
        if not _starts_in_code(code_positions, match.start()):
            continue
        alias = match.group("esm") or match.group("cjs")
        if alias:
            aliases.add(alias)

    findings: list[str] = []
    seen: set[tuple[int, str]] = set()
    for alias in sorted(aliases):
        dot_call_re = re.compile(
            rf"\b{re.escape(alias)}\s*(?:\?\.|\.)\s*exec(?:Sync)?\s*\("
        )
        bracket_call_re = re.compile(
            rf"\b{re.escape(alias)}\s*\[\s*['\"]exec(?:Sync)?['\"]\s*\]\s*\("
        )
        for call_kind, pattern in (("dot", dot_call_re), ("bracket", bracket_call_re)):
            for match in pattern.finditer(scan_text):
                if not _starts_in_code(code_positions, match.start()):
                    continue
                key = (match.start(), alias)
                if key in seen:
                    continue
                seen.add(key)
                notation = " bracket" if call_kind == "bracket" else ""
                findings.append(
                    f"{label}:{_line_number(text, match.start())}: "
                    f"child_process namespace alias {alias}{notation} exec()/execSync() is forbidden"
                )

    return findings


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in javascript_files():
        scanned += 1
        findings.extend(violations(path))
    if findings:
        print("JavaScript child_process alias violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"JavaScript child_process alias gate passed ({scanned} JS/TS files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
