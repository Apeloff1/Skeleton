"""Dependency-free high-confidence Python/JavaScript/TypeScript SAST gate.

The scanner intentionally targets dangerous primitives with a low false-positive
rate. Broader lint/security tooling can layer on top, but these patterns should
never silently enter production code.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".expo",
    "coverage",
}
TRACKED_MODULES = {"requests", "httpx", "ssl", "tempfile", "jwt"}
REQUESTS_SESSION_CALLS = {
    f"requests.Session.{method}"
    for method in ("get", "post", "put", "patch", "delete", "head", "options", "request")
}
NETWORK_CALLS = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.head",
    "requests.options",
    "requests.request",
    *REQUESTS_SESSION_CALLS,
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
    "httpx.head",
    "httpx.options",
    "httpx.request",
}
JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
JS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "dynamic eval() is forbidden",
        re.compile(r"(?<![A-Za-z0-9_$\.])eval\s*\("),
    ),
    (
        "Function constructor is forbidden",
        re.compile(r"(?<![A-Za-z0-9_$\.])(?:new\s+)?Function\s*\("),
    ),
    (
        "TLS rejectUnauthorized:false is forbidden",
        re.compile(r"\brejectUnauthorized\s*:\s*false\b"),
    ),
    (
        "NODE_TLS_REJECT_UNAUTHORIZED=0 is forbidden",
        re.compile(
            r"\bprocess\s*\.\s*env\s*\.\s*NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]0['\"]"
        ),
    ),
    (
        "child_process.exec()/execSync() is forbidden",
        re.compile(r"\bchild_process\s*\.\s*exec(?:Sync)?\s*\("),
    ),
    (
        "require('child_process').exec()/execSync() is forbidden",
        re.compile(
            r"\brequire\s*\(\s*['\"](?:node:)?child_process['\"]\s*\)\s*\.\s*exec(?:Sync)?\s*\("
        ),
    ),
)
CHILD_PROCESS_IMPORT_RE = re.compile(
    r"(?:import\s*\{(?P<esm>[^}]*)\}\s*from\s*['\"](?:node:)?child_process['\"]"
    r"|(?:const|let|var)\s*\{(?P<cjs>[^}]*)\}\s*=\s*require\s*\(\s*['\"](?:node:)?child_process['\"]\s*\))"
)


def python_files() -> Iterable[Path]:
    for path in BACKEND_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


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


def dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in TRACKED_MODULES:
                    aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root not in TRACKED_MODULES:
                continue
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def canonical_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Resolve tracked imports and methods invoked on inline constructors.

    ``dotted_name`` intentionally handles only Name/Attribute chains. Security
    rules also need to recognize calls such as ``requests.Session().get(...)``;
    the owner of that final attribute is an ``ast.Call`` rather than a Name.
    Resolving only the constructor function keeps this high-confidence without
    attempting general data-flow inference.
    """
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call):
        owner = canonical_name(node.value.func, aliases)
        if owner:
            return f"{owner}.{node.attr}"

    name = dotted_name(node)
    if not name:
        return None
    root, dot, suffix = name.partition(".")
    replacement = aliases.get(root)
    if replacement is None:
        return name
    return replacement + (f".{suffix}" if dot else "")


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _literal_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _dict_disables_signature_verification(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    for key, value in zip(node.keys, node.values):
        if (
            isinstance(key, ast.Constant)
            and key.value in {"verify_signature", "verify"}
            and _literal_false(value)
        ):
            return True
    return False


def call_violation(node: ast.Call, aliases: dict[str, str]) -> str | None:
    name = canonical_name(node.func, aliases)

    if name in {"eval", "exec"}:
        return f"{name}() is forbidden in backend production code"

    if name == "tempfile.mktemp":
        return "tempfile.mktemp() is race-prone; use NamedTemporaryFile or mkstemp"

    if name == "ssl._create_unverified_context":
        return "ssl._create_unverified_context() disables certificate verification"

    if name in NETWORK_CALLS and _literal_false(_keyword(node, "verify")):
        return f"{name}(..., verify=False) is forbidden"

    if name in {"httpx.Client", "httpx.AsyncClient"} and _literal_false(_keyword(node, "verify")):
        return f"{name}(..., verify=False) is forbidden"

    if name in {"jwt.decode", "jwt.api_jwt.decode_complete"}:
        if _dict_disables_signature_verification(_keyword(node, "options")):
            return f"{name}() must not disable signature verification"

    return None


def violations(path: Path) -> list[str]:
    """Return high-confidence Python findings for ``path``."""
    label = display_path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [f"{label}: parse failure: {exc}"]

    aliases = import_aliases(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        violation = call_violation(node, aliases)
        if violation:
            findings.append(f"{label}:{node.lineno}: {violation}")
    return findings


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _mask_js_comments(text: str) -> str:
    """Replace JS/TS comment bytes with spaces while preserving offsets/newlines.

    Regex rules can then inspect executable source without matching documentation
    such as ``module-eval (which...)``. String and template contents are kept
    intact so module specifiers used by child-process rules remain discoverable.
    """
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
            escaped = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            out[i] = " "
            out[i + 1] = " "
            state = "line-comment"
            i += 2
            continue

        if ch == "/" and nxt == "*":
            out[i] = " "
            out[i + 1] = " "
            state = "block-comment"
            i += 2
            continue

        i += 1

    return "".join(out)


def _destructured_child_process_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in CHILD_PROCESS_IMPORT_RE.finditer(text):
        declaration = match.group("esm") or match.group("cjs") or ""
        for raw_item in declaration.split(","):
            item = raw_item.strip()
            if not item:
                continue
            # ESM: exec as runCommand. CJS: exec: runCommand.
            if " as " in item:
                source, local = (piece.strip() for piece in item.split(" as ", 1))
            elif ":" in item:
                source, local = (piece.strip() for piece in item.split(":", 1))
            else:
                source = local = item
            if source in {"exec", "execSync"} and re.fullmatch(r"[A-Za-z_$][\w$]*", local):
                names.add(local)
    return names


def javascript_violations(path: Path) -> list[str]:
    """Return low-noise JavaScript/TypeScript security findings for ``path``."""
    label = display_path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{label}: read failure: {exc}"]

    scan_text = _mask_js_comments(text)
    findings: list[str] = []
    for message, pattern in JS_PATTERNS:
        for match in pattern.finditer(scan_text):
            findings.append(f"{label}:{_line_number(text, match.start())}: {message}")

    for local_name in sorted(_destructured_child_process_names(scan_text)):
        call_re = re.compile(rf"(?<![A-Za-z0-9_$\.]){re.escape(local_name)}\s*\(")
        for match in call_re.finditer(scan_text):
            findings.append(
                f"{label}:{_line_number(text, match.start())}: imported child_process {local_name}() is forbidden"
            )

    # A shell-enabled spawn crosses the same command-interpreter trust boundary
    # as exec. Restrict this rule to files that actually reference child_process
    # to avoid flagging unrelated configuration objects with `shell: true`.
    if re.search(r"['\"](?:node:)?child_process['\"]|\bchild_process\b", scan_text):
        shell_true = re.compile(r"\bshell\s*:\s*true\b")
        for match in shell_true.finditer(scan_text):
            findings.append(
                f"{label}:{_line_number(text, match.start())}: child_process shell:true is forbidden"
            )

    return findings


def main() -> int:
    findings: list[str] = []
    python_count = 0
    js_count = 0
    for path in python_files():
        python_count += 1
        findings.extend(violations(path))
    for path in javascript_files():
        js_count += 1
        findings.extend(javascript_violations(path))
    if findings:
        print("High-confidence SAST violations detected:", file=sys.stderr)
        for finding in sorted(findings):
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"High-confidence SAST gate passed ({python_count} Python, {js_count} JS/TS files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
