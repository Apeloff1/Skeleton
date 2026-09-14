"""Reject JavaScript/TypeScript child_process namespace aliases that hide shell execution.

The primary SAST gate catches direct ``child_process.exec`` calls and destructured
``exec``/``execSync`` imports. This companion gate closes namespace-alias bypasses
while keeping false positives low by distinguishing executable code from comments
and string/template contents.
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


def _mask_non_code(text: str, *, mask_strings: bool) -> str:
    """Mask comments and optionally strings while preserving offsets/newlines."""
    chars = list(text)
    out = list(text)
    state = "code"
    quote = ""
    escaped = False
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
                out[i] = " "
                out[i + 1] = " "
                state = "code"
                i += 2
                continue
            if ch != "\n":
                out[i] = " "
            i += 1
            continue

        if state == "quoted":
            if mask_strings and ch != "\n":
                out[i] = " "
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                state = "code"
                quote = ""
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            state = "quoted"
            quote = ch
            escaped = False
            if mask_strings:
                out[i] = " "
            i += 1
            continue

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

        i += 1

    return "".join(out)


def _match_starts_in_code(code_text: str, start: int, alias: str) -> bool:
    return code_text[start : start + len(alias)] == alias


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}: read failure: {exc}"]

    # Imports need their module-specifier strings preserved; executable-call
    # matching does not. Keeping separate masks prevents code-like string data
    # from becoming a false positive while still recognizing real imports.
    import_text = _mask_non_code(text, mask_strings=False)
    code_text = _mask_non_code(text, mask_strings=True)

    aliases: set[str] = set()
    for match in NAMESPACE_IMPORT_RE.finditer(import_text):
        alias = match.group("esm") or match.group("cjs")
        if alias:
            aliases.add(alias)

    findings: list[str] = []
    seen: set[tuple[int, str]] = set()
    for alias in sorted(aliases):
        dot_call_re = re.compile(
            rf"\b{re.escape(alias)}\s*(?:\?\.|\.)\s*exec(?:Sync)?\s*\("
        )
        for match in dot_call_re.finditer(code_text):
            key = (match.start(), alias)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                f"{label}:{_line_number(text, match.start())}: "
                f"child_process namespace alias {alias}.exec()/execSync() is forbidden"
            )

        # Bracket notation contains a real string token (cp['exec']()), so scan
        # the comment-masked source and prove the alias itself starts in code.
        bracket_call_re = re.compile(
            rf"\b{re.escape(alias)}\s*\[\s*['\"]exec(?:Sync)?['\"]\s*\]\s*\("
        )
        for match in bracket_call_re.finditer(import_text):
            if not _match_starts_in_code(code_text, match.start(), alias):
                continue
            key = (match.start(), alias)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                f"{label}:{_line_number(text, match.start())}: "
                f"child_process namespace alias {alias} bracket exec()/execSync() is forbidden"
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
