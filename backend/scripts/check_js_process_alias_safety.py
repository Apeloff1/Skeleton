"""Reject JavaScript/TypeScript child_process namespace aliases that hide shell execution.

The primary SAST gate catches direct ``child_process.exec`` calls and destructured
``exec``/``execSync`` imports. This companion gate closes the namespace-alias gap:

    import * as cp from "node:child_process";
    cp.exec(userInput);

and the equivalent CommonJS ``const cp = require(...)`` form. It is deliberately
small and dependency-free so it can run in the earliest quality phase.
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
    rf"\bimport\s*\*\s*as\s*(?P<esm>{IDENTIFIER})\s*from\s*['\"](?:node:)?child_process['\"]"
    rf"|\b(?:const|let|var)\s+(?P<cjs>{IDENTIFIER})\s*=\s*require\s*\(\s*['\"](?:node:)?child_process['\"]\s*\)"
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
    """Mask JS comments while preserving strings, offsets, and line numbers."""
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


def violations(path: Path) -> list[str]:
    label = display_path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}: read failure: {exc}"]

    scan_text = _mask_comments(text)
    aliases: set[str] = set()
    for match in NAMESPACE_IMPORT_RE.finditer(scan_text):
        alias = match.group("esm") or match.group("cjs")
        if alias:
            aliases.add(alias)

    findings: list[str] = []
    for alias in sorted(aliases):
        exec_re = re.compile(rf"\b{re.escape(alias)}\s*\.\s*exec(?:Sync)?\s*\(")
        for match in exec_re.finditer(scan_text):
            findings.append(
                f"{label}:{_line_number(text, match.start())}: "
                f"child_process namespace alias {alias}.exec()/execSync() is forbidden"
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
