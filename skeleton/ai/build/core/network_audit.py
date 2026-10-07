"""Fail-closed audit of build/test commands that require network.

Seed: SHIFT-PROMOTION-SEED #969 Seed 10 (reserve-S026-build-network-audit).

The scanner reads ``scripts/``, the root Makefile, GitHub workflows, and
pytest/npm command texts. It never executes those commands. Unknown commands
are ``network-unknown`` and are never classified ``offline`` without evidence.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, Mapping, Sequence

TASK_ID = "reserve-S026-build-network-audit"
CONFLICT_DOMAIN = "build.readonly.network_dependencies"
KIND = "build_network_audit"
SCHEMA_VERSION = 1

CLASSIFICATION_NETWORK_REQUIRED = "network-required"
CLASSIFICATION_OFFLINE = "offline"
CLASSIFICATION_NETWORK_UNKNOWN = "network-unknown"

CLASSIFICATIONS = (
    CLASSIFICATION_NETWORK_REQUIRED,
    CLASSIFICATION_OFFLINE,
    CLASSIFICATION_NETWORK_UNKNOWN,
)

SOURCE_SCRIPT = "script"
SOURCE_MAKEFILE = "makefile"
SOURCE_WORKFLOW = "workflow"
SOURCE_NPM = "npm"

_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_URL_RE = re.compile(r"""(?:https?|git|ssh|ftp|sftp|ftps)://[^\s'"`]+""", re.IGNORECASE)
_HOST_RE = re.compile(
    r"""(?<![A-Za-z0-9_./@-])(?:[A-Za-z0-9-]+\.)+(?:com|net|org|io|dev|ai|info|edu|gov|xyz)(?::\d{2,5})?(?:/|\b)""",
    re.IGNORECASE,
)
_ENV_ASSIGN_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|[^\s;]+)\s+)+")
_USES_RE = re.compile(
    r"""^\s*(?:-\s*)?(?:\{\s*)?(?:uses|'uses'|"uses")\s*:\s*["']?([^"'\s,}#]+)"""
)
_FLOW_USES_RE = re.compile(r"""(?:uses|'uses'|"uses")\s*:\s*["']?([^"'\s,}#]+)""")
_IMAGE_RE = re.compile(r"""^\s*(?:image|'image'|"image")\s*:\s*["']?([^"'\s#]+)""")
_NPM_INSTALL_RE = re.compile(
    r"^(?:npm|npx|pnpm|yarn|bun)\s+(?:install|ci|add|update|upgrade|audit|publish)\b",
    re.IGNORECASE,
)
_PIP_INSTALL_RE = re.compile(
    r"""(?:(?:python(?:3(\.\d+)?)?|py)\s+-m\s+)?(?:pip3?|uv\s+pip)\s+install\b""",
    re.IGNORECASE,
)
_UVX_RE = re.compile(r"\buvx\b", re.IGNORECASE)
_GIT_REMOTE_RE = re.compile(r"\bgit\s+(?:clone|fetch|pull|push|ls-remote)\b", re.IGNORECASE)
_DOCKER_PULL_RE = re.compile(r"\bdocker\s+(?:pull|login|push|build)\b", re.IGNORECASE)
_NETWORK_BINARIES = frozenset(
    {
        "curl",
        "wget",
        "aria2c",
        "nc",
        "ncat",
        "netcat",
        "ssh",
        "scp",
        "sftp",
        "rsync",
        "ftp",
        "ping",
        "traceroute",
        "nslookup",
        "dig",
        "host",
        "telnet",
        "nmap",
    }
)
_OFFLINE_BINARIES = frozenset(
    {
        "true",
        "false",
        "echo",
        "printf",
        "chmod",
        "mkdir",
        "rm",
        "rmdir",
        "touch",
        "ls",
        "cat",
        "cp",
        "mv",
        "ln",
        "test",
        ":",
        "set",
        "unset",
        "export",
        "cd",
        "pwd",
        "basename",
        "dirname",
        "head",
        "tail",
        "sort",
        "uniq",
        "wc",
        "tee",
        "sleep",
        "date",
        "cut",
        "tr",
        "awk",
        "sed",
        "cmp",
        "diff",
        "stat",
        "find",
        "xargs",
    }
)
_OFFLINE_PYTHON_MODULES = frozenset({"compileall", "py_compile", "unittest", "pytest"})
_OFFLINE_NPM_FLAGS = frozenset({"--offline", "--prefer-offline"})
_PACKAGE_MANAGER_BINARIES = frozenset(
    {"apt-get", "apt", "yum", "dnf", "apk", "brew", "pacman", "sdkmanager"}
)
_PYTHON_C_LOCAL_ROOTS = frozenset(
    {
        "skeleton",
        "sys",
        "json",
        "math",
        "decimal",
        "typing",
        "collections",
        "dataclasses",
        "enum",
        "re",
        "ast",
    }
)
_PYTHON_C_LOCAL_CALLS = frozenset(
    {
        "print",
        "len",
        "str",
        "int",
        "list",
        "tuple",
        "dict",
        "set",
        "getattr",
        "hasattr",
        "isinstance",
        "repr",
        "sorted",
        "min",
        "max",
        "hex",
        "id",
        "bool",
        "type",
    }
)
_SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".ksh", ".command"}
_SHELL_SHEBANG_MARKERS = ("/sh", "/bash", "/zsh", "/ksh", "/dash", " env sh", " env bash")
_SHELL_SYNTAX_LEADERS = frozenset(
    {"if", "then", "else", "elif", "fi", "do", "done", "case", "esac", "in"}
)

_SCAN_SCRIPTS_DIR = "scripts"
_SCAN_MAKEFILE = "Makefile"
_SCAN_WORKFLOWS_DIR = Path(".github") / "workflows"
_SCAN_PACKAGE_JSON = (Path("package.json"), Path("frontend") / "package.json")

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "dist",
        "build",
    }
)


@dataclass(frozen=True, slots=True)
class CommandFinding:
    path: str
    line: int
    source_kind: str
    excerpt: str
    classification: str
    reasons: tuple[str, ...]
    hidden: bool

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True, slots=True)
class NetworkAuditReport:
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND
    task_key: str = TASK_ID
    conflict_domain: str = CONFLICT_DOMAIN
    fail_closed: bool = True
    scanned_files: tuple[str, ...] = ()
    findings: tuple[CommandFinding, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "task_key": self.task_key,
            "conflict_domain": self.conflict_domain,
            "fail_closed": self.fail_closed,
            "scanned_files": list(self.scanned_files),
            "findings": [item.to_payload() for item in self.findings],
            "counts": dict(self.counts),
        }


def classify_command(command: str) -> tuple[str, tuple[str, ...]]:
    """Return ``(classification, evidence_reasons)`` for one command string.

    Unknown commands are ``network-unknown``. ``offline`` is returned only when
    every token is covered by local-only evidence and no network signal exists.
    """

    text = _strip_line_comment(command).strip()
    if not text:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("empty-command",)
    if text.startswith("!"):
        text = text[1:].lstrip()

    reasons: list[str] = []
    for segment in _split_command_list(text):
        classification, segment_reasons = _classify_one(segment)
        if classification == CLASSIFICATION_NETWORK_REQUIRED:
            return classification, segment_reasons
        reasons.extend(segment_reasons)
        if classification == CLASSIFICATION_NETWORK_UNKNOWN:
            return CLASSIFICATION_NETWORK_UNKNOWN, tuple(dict.fromkeys(segment_reasons or ("no-offline-evidence",)))

    unique = tuple(dict.fromkeys(reasons))
    if unique and all(reason.startswith("offline-") for reason in unique):
        return CLASSIFICATION_OFFLINE, unique
    return CLASSIFICATION_NETWORK_UNKNOWN, unique or ("no-offline-evidence",)


def classify_action_ref(reference: str) -> tuple[str, tuple[str, ...], bool]:
    """Classify a GitHub Actions ``uses:`` / image reference.

    Returns ``(classification, reasons, hidden)``. Local path actions are
    offline. Unpinned remote downloads are hidden network. SHA-pinned remote
    actions still require a fetch, so they stay ``network-required`` but are
    not hidden.
    """

    ref = reference.strip().strip("\"'")
    if not ref:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("empty-action-ref",), True
    if ref.startswith("./") or ref.startswith(".\\"):
        return CLASSIFICATION_OFFLINE, ("offline-local-action",), False
    if ref.startswith("docker://"):
        image = ref.removeprefix("docker://")
        if "@sha256:" in image:
            digest = image.rsplit("@sha256:", 1)[1]
            if _SHA256_RE.fullmatch(digest):
                return CLASSIFICATION_NETWORK_REQUIRED, ("pinned-container-download",), False
            return CLASSIFICATION_NETWORK_REQUIRED, ("unpinned-container-download",), True
        return CLASSIFICATION_NETWORK_REQUIRED, ("unpinned-container-download",), True
    if "/" not in ref and not ref.startswith("docker://"):
        return CLASSIFICATION_NETWORK_UNKNOWN, ("malformed-action-ref",), True

    if "@" not in ref:
        return CLASSIFICATION_NETWORK_REQUIRED, ("unpinned-action-download",), True
    _name, pin = ref.rsplit("@", 1)
    pin = pin.strip()
    if _SHA40_RE.fullmatch(pin):
        return CLASSIFICATION_NETWORK_REQUIRED, ("pinned-github-action",), False
    return CLASSIFICATION_NETWORK_REQUIRED, ("unpinned-action-download",), True


def audit_repository(root: str | Path | None = None) -> NetworkAuditReport:
    """Scan canonical build/test surfaces. Never executes discovered commands."""

    base = Path(root) if root is not None else _default_repo_root()
    findings: list[CommandFinding] = []
    scanned: list[str] = []

    scripts_dir = base / _SCAN_SCRIPTS_DIR
    if scripts_dir.is_dir():
        for path in _iter_files(scripts_dir):
            if not _is_shell_script(path):
                continue
            scanned.append(_rel(base, path))
            findings.extend(_scan_script(path, base))

    makefile = base / _SCAN_MAKEFILE
    if makefile.is_file():
        scanned.append(_rel(base, makefile))
        findings.extend(_scan_makefile(makefile, base))

    workflows = base / _SCAN_WORKFLOWS_DIR
    if workflows.is_dir():
        for path in _iter_files(workflows, suffixes={".yml", ".yaml"}):
            scanned.append(_rel(base, path))
            findings.extend(_scan_workflow(path, base))

    for relative in _SCAN_PACKAGE_JSON:
        path = base / relative
        if path.is_file():
            scanned.append(_rel(base, path))
            findings.extend(_scan_package_json(path, base))

    counts = {
        CLASSIFICATION_NETWORK_REQUIRED: 0,
        CLASSIFICATION_OFFLINE: 0,
        CLASSIFICATION_NETWORK_UNKNOWN: 0,
        "hidden_network_required": 0,
    }
    for finding in findings:
        counts[finding.classification] = counts.get(finding.classification, 0) + 1
        if finding.hidden and finding.classification == CLASSIFICATION_NETWORK_REQUIRED:
            counts["hidden_network_required"] += 1

    scanned_sorted = tuple(sorted(dict.fromkeys(scanned)))
    findings_sorted = tuple(
        sorted(findings, key=lambda item: (item.path, item.line, item.excerpt, item.classification))
    )
    return NetworkAuditReport(
        scanned_files=scanned_sorted,
        findings=findings_sorted,
        counts=counts,
    )


def network_audit_snapshot(root: str | Path | None = None) -> dict[str, object]:
    return audit_repository(root).to_payload()


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rel(base: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_shell_script(path: Path) -> bool:
    if path.suffix.lower() in _SHELL_SUFFIXES:
        return True
    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline(120)
    except (OSError, UnicodeError):
        return False
    if not first.startswith("#!"):
        return False
    lowered = first.lower()
    if "python" in lowered:
        return False
    return any(marker in lowered for marker in _SHELL_SHEBANG_MARKERS)


def _iter_files(root: Path, suffixes: set[str] | None = None) -> Iterator[Path]:
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        yield path


def _strip_line_comment(text: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(text):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or text[index - 1].isspace():
                return text[:index].rstrip()
    return text.rstrip()


def _split_command_list(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    dollar_depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'" and not in_double:
            in_single = not in_single
            buf.append(char)
        elif char == '"' and not in_single:
            in_double = not in_double
            buf.append(char)
        elif not in_single and not in_double:
            if text.startswith("$(", index):
                dollar_depth += 1
                buf.append("$(")
                index += 2
                continue
            if char == ")" and dollar_depth:
                dollar_depth -= 1
                buf.append(char)
                index += 1
                continue
            if dollar_depth:
                buf.append(char)
                index += 1
                continue
            if text.startswith("&&", index) or text.startswith("||", index):
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                index += 2
                continue
            if char in {";", "\n"}:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                index += 1
                continue
            if char == "|" and not text.startswith("||", index):
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                index += 1
                continue
            buf.append(char)
        else:
            buf.append(char)
        index += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts or [text.strip()]


def _tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _strip_env_prefix(command: str) -> str:
    match = _ENV_ASSIGN_RE.match(command.strip())
    if not match:
        return command.strip()
    return command.strip()[match.end() :].strip()


def _binary_name(token: str) -> str:
    name = Path(token).name
    if name.endswith(".exe"):
        name = name[:-4]
    return name.lower()


def _looks_like_url_or_host(text: str) -> bool:
    if _URL_RE.search(text):
        return True
    return _HOST_RE.search(text) is not None


def _pip_offline(tokens: Sequence[str]) -> bool:
    lowered = [token.lower() for token in tokens]
    if "--offline" in lowered or "--no-index" in lowered:
        return True
    return False


def _npm_offline(tokens: Sequence[str]) -> bool:
    lowered = [token.lower() for token in tokens]
    return any(flag in lowered for flag in _OFFLINE_NPM_FLAGS)


def _classify_one(command: str) -> tuple[str, tuple[str, ...]]:
    text = _strip_line_comment(command).strip()
    if not text:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("empty-command",)
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = _strip_env_prefix(text)
    if text.startswith("sudo "):
        text = text[5:].lstrip()
    if text.startswith("command "):
        text = text[8:].lstrip()
    if text.startswith("exec "):
        text = text[5:].lstrip()
    if not text:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("empty-command",)

    if _URL_RE.search(text):
        return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
    if _PIP_INSTALL_RE.search(text):
        tokens = _tokenize(text)
        if _pip_offline(tokens):
            return CLASSIFICATION_OFFLINE, ("offline-pip-install",)
        return CLASSIFICATION_NETWORK_REQUIRED, ("pip-install-without-offline",)
    if _UVX_RE.search(text):
        return CLASSIFICATION_NETWORK_REQUIRED, ("uvx-package-download",)
    if _NPM_INSTALL_RE.search(text):
        tokens = _tokenize(text)
        if _npm_offline(tokens):
            return CLASSIFICATION_OFFLINE, ("offline-npm-install",)
        return CLASSIFICATION_NETWORK_REQUIRED, ("npm-install-without-offline",)
    if _GIT_REMOTE_RE.search(text):
        return CLASSIFICATION_NETWORK_REQUIRED, ("git-remote-operation",)
    if _DOCKER_PULL_RE.search(text):
        return CLASSIFICATION_NETWORK_REQUIRED, ("docker-registry-operation",)
    if _HOST_RE.search(text):
        return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)

    tokens = _tokenize(text)
    if not tokens:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("empty-command",)

    binary = _binary_name(tokens[0])
    if binary in _SHELL_SYNTAX_LEADERS:
        remainder = " ".join(tokens[1:]).lstrip("!").strip()
        if remainder:
            return _classify_one(remainder)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("shell-syntax",)
    if binary in _PACKAGE_MANAGER_BINARIES:
        joined = " ".join(tokens).lower()
        if binary == "sdkmanager" or any(
            verb in joined for verb in (" install", " update", " upgrade", " add")
        ):
            return CLASSIFICATION_NETWORK_REQUIRED, ("package-manager-install",)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("package-manager-unknown",)
    if binary in {"python", "py"} or binary.startswith("python3"):
        return _classify_python(tokens[1:])
    if binary in _NETWORK_BINARIES:
        return CLASSIFICATION_NETWORK_REQUIRED, (f"network-binary:{binary}",)
    if binary in {"pip", "pip3"}:
        if len(tokens) >= 2 and tokens[1].lower() == "install":
            if _pip_offline(tokens):
                return CLASSIFICATION_OFFLINE, ("offline-pip-install",)
            return CLASSIFICATION_NETWORK_REQUIRED, ("pip-install-without-offline",)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("pip-subcommand-unknown",)
    if binary in {"npm", "npx", "pnpm", "yarn", "bun"}:
        return _classify_node(tokens)
    if binary in {"pytest"}:
        if _looks_like_url_or_host(" ".join(tokens[1:])):
            return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
        return CLASSIFICATION_OFFLINE, ("offline-pytest-runner",)
    if binary in {"make"}:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("make-target-unknown",)
    if binary in {"bash", "sh", "dash", "zsh", "ksh"}:
        return _classify_shell_invocation(tokens)
    if binary in _OFFLINE_BINARIES:
        remainder = " ".join(tokens[1:])
        if _looks_like_url_or_host(remainder) or any(_binary_name(tok) in _NETWORK_BINARIES for tok in tokens[1:]):
            return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
        return CLASSIFICATION_OFFLINE, (f"offline-binary:{binary}",)
    return CLASSIFICATION_NETWORK_UNKNOWN, ("no-offline-evidence",)


def _classify_python(args: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    if not args:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("python-args-missing",)
    if args[0] == "-m" and len(args) >= 2:
        module = args[1]
        rest = args[2:]
        if module in {"pip", "pip3"}:
            joined = "python -m " + " ".join(args[1:])
            if _PIP_INSTALL_RE.search(joined) and _pip_offline(args):
                return CLASSIFICATION_OFFLINE, ("offline-pip-install",)
            if module == "pip" and rest and rest[0] == "install":
                return CLASSIFICATION_NETWORK_REQUIRED, ("pip-install-without-offline",)
            return CLASSIFICATION_NETWORK_UNKNOWN, ("pip-subcommand-unknown",)
        if module in {"http.server", "xmlrpc.server", "wsgiref.simple_server"}:
            return CLASSIFICATION_NETWORK_REQUIRED, ("python-network-module",)
        if module in _OFFLINE_PYTHON_MODULES:
            if _looks_like_url_or_host(" ".join(rest)):
                return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
            return CLASSIFICATION_OFFLINE, (f"offline-python-module:{module}",)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("python-module-unknown",)
    if args[0] == "-c" and len(args) >= 2:
        snippet = args[1]
        if _looks_like_url_or_host(snippet) or _python_snippet_networks(snippet):
            return CLASSIFICATION_NETWORK_REQUIRED, ("python-c-network",)
        if _python_snippet_local(snippet):
            return CLASSIFICATION_OFFLINE, ("offline-python-c-local",)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("python-c-unknown",)
    if args[0].startswith("-") and "-m" not in args and "-c" not in args:
        if _looks_like_url_or_host(" ".join(args)):
            return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
        return CLASSIFICATION_NETWORK_UNKNOWN, ("python-flags-unknown",)
    if _looks_like_url_or_host(" ".join(args)):
        return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
    return CLASSIFICATION_NETWORK_UNKNOWN, ("python-script-unknown",)


def _python_snippet_networks(snippet: str) -> bool:
    lowered = snippet.lower()
    needles = (
        "urllib",
        "http.client",
        "httpx",
        "requests",
        "aiohttp",
        "socket.create_connection",
        "websocket",
        "ftp",
        "subprocess",
        "os.system",
    )
    return any(needle in lowered for needle in needles)


def _python_snippet_local(snippet: str) -> bool:
    """Conservative local-only python -c evidence (allowlisted imports/prints)."""

    try:
        import ast
    except ImportError:  # pragma: no cover - stdlib
        return False
    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in _PYTHON_C_LOCAL_ROOTS:
                    return False
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root not in _PYTHON_C_LOCAL_ROOTS:
                return False
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id not in _PYTHON_C_LOCAL_CALLS:
                return False
            if isinstance(func, ast.Name) and func.id in {"open", "eval", "exec", "__import__"}:
                return False
    return True


def _classify_node(tokens: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    binary = _binary_name(tokens[0])
    rest = [token for token in tokens[1:] if not token.startswith("-") or token in _OFFLINE_NPM_FLAGS]
    flags_only = tokens[1:]
    if _looks_like_url_or_host(" ".join(tokens[1:])):
        return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
    sub = rest[0].lower() if rest else ""
    if sub in {"install", "ci", "add", "update", "upgrade", "audit", "publish"} or (
        binary == "yarn" and (not rest or rest[0].startswith("-") or sub in {"install"})
    ):
        if binary == "yarn" and rest and rest[0] not in {"install", "add", "upgrade", "audit", "publish", "ci"}:
            if rest[0] in {"--cwd"}:
                return CLASSIFICATION_NETWORK_UNKNOWN, ("npm-script-unknown",)
            return CLASSIFICATION_NETWORK_UNKNOWN, ("npm-script-unknown",)
        if _npm_offline(flags_only) or _npm_offline(tokens):
            return CLASSIFICATION_OFFLINE, ("offline-npm-install",)
        if binary == "yarn" and not rest:
            return CLASSIFICATION_NETWORK_REQUIRED, ("npm-install-without-offline",)
        if sub in {"install", "ci", "add", "update", "upgrade", "audit", "publish"}:
            if _npm_offline(tokens):
                return CLASSIFICATION_OFFLINE, ("offline-npm-install",)
            return CLASSIFICATION_NETWORK_REQUIRED, ("npm-install-without-offline",)
    if sub in {"test", "run", "exec", "lint", "start"}:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("npm-script-unknown",)
    if binary == "yarn" and rest:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("npm-script-unknown",)
    return CLASSIFICATION_NETWORK_UNKNOWN, ("npm-script-unknown",)


def _classify_shell_invocation(tokens: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    args = tokens[1:]
    while args and args[0].startswith("-"):
        if args[0] in {"-c", "-lc"}:
            if len(args) < 2:
                return CLASSIFICATION_NETWORK_UNKNOWN, ("shell-c-missing",)
            return _classify_one(args[1])
        args = args[1:]
    if not args:
        return CLASSIFICATION_NETWORK_UNKNOWN, ("shell-args-missing",)
    if _looks_like_url_or_host(" ".join(args)):
        return CLASSIFICATION_NETWORK_REQUIRED, ("live-host",)
    return CLASSIFICATION_NETWORK_UNKNOWN, ("shell-script-unknown",)


def _join_continuations(lines: Sequence[str]) -> list[tuple[int, str]]:
    joined: list[tuple[int, str]] = []
    buffer: str | None = None
    start = 0
    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        logical = line[1:] if line.startswith("\t") else line
        stripped_right = logical.rstrip()
        if buffer is None:
            if stripped_right.endswith("\\") and not stripped_right.lstrip().startswith("#"):
                buffer = stripped_right[:-1].rstrip() + " "
                start = number
            else:
                joined.append((number, line))
        else:
            piece = logical.strip()
            if piece.endswith("\\"):
                buffer += piece[:-1].rstrip() + " "
            else:
                buffer += piece
                prefix = "\t" if lines[start - 1].startswith("\t") else ""
                joined.append((start, prefix + buffer))
                buffer = None
    if buffer is not None:
        prefix = "\t" if lines[start - 1].startswith("\t") else ""
        joined.append((start, prefix + buffer))
    return joined


def _scan_text_commands(
    path: Path,
    base: Path,
    source_kind: str,
    lines: Sequence[str],
) -> list[CommandFinding]:
    findings: list[CommandFinding] = []
    for number, raw in _join_continuations(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for command in _split_command_list(_strip_line_comment(stripped)):
            if not command or command.endswith(":"):
                continue
            if command.startswith("@") and source_kind == SOURCE_MAKEFILE:
                command = command[1:].lstrip()
            classification, reasons = classify_command(command)
            findings.append(
                _finding(
                    path=path,
                    base=base,
                    line=number,
                    source_kind=_source_kind_for_command(source_kind, command),
                    excerpt=_excerpt(command),
                    classification=classification,
                    reasons=reasons,
                )
            )
    return findings


def _source_kind_for_command(default: str, command: str) -> str:
    text = command.lstrip()
    if re.search(r"\bpip(?:3)?\s+install\b", text) or re.search(r"\buv\s+pip\s+install\b", text):
        return default
    if re.search(r"(?:^|[;&|]\s*)(?:python(?:3[\w.]*)?\s+-m\s+)?pytest\b", text):
        return "pytest"
    if re.search(r"(?:^|[;&|]\s*)(?:npm|npx|pnpm|yarn|bun)\b", text):
        return SOURCE_NPM
    return default


def _finding(
    *,
    path: Path,
    base: Path,
    line: int,
    source_kind: str,
    excerpt: str,
    classification: str,
    reasons: tuple[str, ...],
    hidden: bool | None = None,
) -> CommandFinding:
    if hidden is None:
        hidden = classification == CLASSIFICATION_NETWORK_REQUIRED or classification == CLASSIFICATION_NETWORK_UNKNOWN
        if classification == CLASSIFICATION_NETWORK_REQUIRED and set(reasons) <= {
            "pinned-github-action",
            "pinned-container-download",
            "workflow-service-image",
        }:
            hidden = False
        if classification == CLASSIFICATION_OFFLINE:
            hidden = False
    return CommandFinding(
        path=_rel(base, path),
        line=line,
        source_kind=source_kind,
        excerpt=excerpt,
        classification=classification,
        reasons=reasons,
        hidden=hidden,
    )


def _excerpt(command: str, limit: int = 200) -> str:
    compact = " ".join(command.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _scan_script(path: Path, base: Path) -> list[CommandFinding]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [
            CommandFinding(
                path=_rel(base, path),
                line=0,
                source_kind=SOURCE_SCRIPT,
                excerpt="",
                classification=CLASSIFICATION_NETWORK_UNKNOWN,
                reasons=("unreadable-file",),
                hidden=True,
            )
        ]
    return _scan_text_commands(path, base, SOURCE_SCRIPT, text.splitlines())


def _scan_makefile(path: Path, base: Path) -> list[CommandFinding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return [
            CommandFinding(
                path=_rel(base, path),
                line=0,
                source_kind=SOURCE_MAKEFILE,
                excerpt="",
                classification=CLASSIFICATION_NETWORK_UNKNOWN,
                reasons=("unreadable-file",),
                hidden=True,
            )
        ]
    findings: list[CommandFinding] = []
    for number, raw in _join_continuations(lines):
        if not raw.startswith("\t"):
            continue
        recipe = raw[1:]
        stripped = recipe.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("@"):
            stripped = stripped[1:].lstrip()
        for command in _split_command_list(_strip_line_comment(stripped)):
            classification, reasons = classify_command(command)
            findings.append(
                _finding(
                    path=path,
                    base=base,
                    line=number,
                    source_kind=_source_kind_for_command(SOURCE_MAKEFILE, command),
                    excerpt=_excerpt(command),
                    classification=classification,
                    reasons=reasons,
                )
            )
    return findings


def _scan_workflow(path: Path, base: Path) -> list[CommandFinding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return [
            CommandFinding(
                path=_rel(base, path),
                line=0,
                source_kind=SOURCE_WORKFLOW,
                excerpt="",
                classification=CLASSIFICATION_NETWORK_UNKNOWN,
                reasons=("unreadable-file",),
                hidden=True,
            )
        ]
    findings: list[CommandFinding] = []
    findings.extend(_scan_workflow_uses(path, base, lines))
    findings.extend(_scan_workflow_images(path, base, lines))
    findings.extend(_scan_workflow_run_blocks(path, base, lines))
    return findings


def _scan_workflow_uses(path: Path, base: Path, lines: Sequence[str]) -> list[CommandFinding]:
    findings: list[CommandFinding] = []
    for number, raw in enumerate(lines, start=1):
        match = _USES_RE.match(raw)
        refs = []
        if match:
            refs.append(match.group(1))
        else:
            refs.extend(_FLOW_USES_RE.findall(raw))
        for ref in refs:
            classification, reasons, hidden = classify_action_ref(ref)
            findings.append(
                _finding(
                    path=path,
                    base=base,
                    line=number,
                    source_kind=SOURCE_WORKFLOW,
                    excerpt=_excerpt(f"uses: {ref}"),
                    classification=classification,
                    reasons=reasons,
                    hidden=hidden,
                )
            )
    return findings


def _scan_workflow_images(path: Path, base: Path, lines: Sequence[str]) -> list[CommandFinding]:
    findings: list[CommandFinding] = []
    for number, raw in enumerate(lines, start=1):
        match = _IMAGE_RE.match(raw)
        if not match:
            continue
        image = match.group(1).strip().strip("\"'")
        if "@sha256:" in image:
            digest = image.rsplit("@sha256:", 1)[1]
            if _SHA256_RE.fullmatch(digest):
                classification, reasons, hidden = (
                    CLASSIFICATION_NETWORK_REQUIRED,
                    ("pinned-container-download",),
                    False,
                )
            else:
                classification, reasons, hidden = (
                    CLASSIFICATION_NETWORK_REQUIRED,
                    ("unpinned-container-download",),
                    True,
                )
        else:
            classification, reasons, hidden = (
                CLASSIFICATION_NETWORK_REQUIRED,
                ("unpinned-container-download",),
                True,
            )
        findings.append(
            _finding(
                path=path,
                base=base,
                line=number,
                source_kind=SOURCE_WORKFLOW,
                excerpt=_excerpt(f"image: {image}"),
                classification=classification,
                reasons=reasons,
                hidden=hidden,
            )
        )
    return findings


def _scan_workflow_run_blocks(path: Path, base: Path, lines: Sequence[str]) -> list[CommandFinding]:
    findings: list[CommandFinding] = []
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        run_match = re.match(r"""^(?:-\s*)?(?:run|'run'|"run")\s*:\s*(.*)$""", stripped)
        if not run_match:
            index += 1
            continue
        value = run_match.group(1).strip()
        line_no = index + 1
        if value in {"|", ">", ">-", "|-", "|+"}:
            folded = value.startswith(">")
            block_indent = len(raw) - len(raw.lstrip(" "))
            index += 1
            block_lines: list[tuple[int, str]] = []
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    index += 1
                    continue
                indent = len(nxt) - len(nxt.lstrip(" "))
                if indent <= block_indent:
                    break
                block_lines.append((index + 1, nxt.strip()))
                index += 1
            if folded and block_lines:
                joined = " ".join(text for _number, text in block_lines)
                findings.extend(_findings_from_run_line(path, base, block_lines[0][0], joined))
            else:
                for number, command_line in block_lines:
                    findings.extend(_findings_from_run_line(path, base, number, command_line))
            continue
        if value:
            findings.extend(_findings_from_run_line(path, base, line_no, value.strip("\"'")))
        index += 1
    return findings


def _findings_from_run_line(
    path: Path,
    base: Path,
    line: int,
    command_line: str,
) -> list[CommandFinding]:
    findings: list[CommandFinding] = []
    cleaned = _strip_line_comment(command_line).strip()
    if not cleaned or cleaned.startswith("#"):
        return findings
    for command in _split_command_list(cleaned):
        classification, reasons = classify_command(command)
        findings.append(
            _finding(
                path=path,
                base=base,
                line=line,
                source_kind=_source_kind_for_command(SOURCE_WORKFLOW, command),
                excerpt=_excerpt(command),
                classification=classification,
                reasons=reasons,
            )
        )
    return findings


def _scan_package_json(path: Path, base: Path) -> list[CommandFinding]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [
            CommandFinding(
                path=_rel(base, path),
                line=0,
                source_kind=SOURCE_NPM,
                excerpt="",
                classification=CLASSIFICATION_NETWORK_UNKNOWN,
                reasons=("unreadable-file",),
                hidden=True,
            )
        ]
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return []
    findings: list[CommandFinding] = []
    for name, body in scripts.items():
        if not isinstance(name, str) or not isinstance(body, str):
            findings.append(
                CommandFinding(
                    path=_rel(base, path),
                    line=0,
                    source_kind=SOURCE_NPM,
                    excerpt=str(name),
                    classification=CLASSIFICATION_NETWORK_UNKNOWN,
                    reasons=("npm-script-unknown",),
                    hidden=True,
                )
            )
            continue
        classification, reasons = classify_command(body)
        findings.append(
            _finding(
                path=path,
                base=base,
                line=0,
                source_kind=SOURCE_NPM,
                excerpt=_excerpt(f"{name}: {body}"),
                classification=classification,
                reasons=reasons,
            )
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fail-closed hidden network build audit")
    parser.add_argument("--root", default=None, help="Repository root to scan")
    args = parser.parse_args(argv)
    report = audit_repository(args.root)
    print(json.dumps(report.to_payload(), indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
