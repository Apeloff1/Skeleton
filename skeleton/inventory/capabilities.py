"""Fail-closed static inventory of module and workflow capability surfaces.

Classifies tracked Python modules and GitHub Actions workflows for network,
filesystem-write, subprocess, GitHub mutation, model API, and secret access.

Unknown stays unknown. Absence is claimed only after a file is fully parsed
with no opaque constructs. The classifier is stdlib-only, performs no network
I/O, and does not mutate GitHub.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence


SCHEMA_VERSION: Final = 1
TASK_ID: Final = "reserve-S019-capability-inventory"
CONFLICT_DOMAIN: Final = "security.readonly.capability_inventory"

CAPABILITY_NAMES: Final[tuple[str, ...]] = (
    "network",
    "filesystem_write",
    "subprocess",
    "github_mutation",
    "model_api",
    "secret_access",
)
VERDICTS: Final[tuple[str, ...]] = ("present", "absent", "unknown")
_CAPABILITY_SET: Final = frozenset(CAPABILITY_NAMES)
_VERDICT_SET: Final = frozenset(VERDICTS)

DEFAULT_SCAN_ROOTS: Final[tuple[str, ...]] = ("skeleton", ".github/workflows")
SKIP_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
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
        "satellites",
    }
)
MAX_FILE_BYTES: Final = 1_048_576

_PYTHON_SUFFIXES: Final = frozenset({".py"})
_WORKFLOW_SUFFIXES: Final = frozenset({".yml", ".yaml"})
_WORKFLOW_DIR_PARTS: Final = (".github", "workflows")

_SECRET_FILENAMES: Final = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials.json",
        "credentials.yml",
        "credentials.yaml",
        "service-account.json",
    }
)
_SECRET_SUFFIXES: Final = frozenset({".pem", ".p12", ".pfx", ".key"})
_SECRET_DIR_PARTS: Final = frozenset({".ssh", ".gnupg", ".aws", ".secrets"})

_NETWORK_MODULES: Final = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "http.client",
        "http.server",
        "http.cookiejar",
        "urllib",
        "urllib.request",
        "urllib.error",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "websocket",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "nntplib",
        "grpc",
        "paramiko",
        "asyncssh",
        "socketserver",
    }
)
_SUBPROCESS_MODULES: Final = frozenset({"subprocess", "pty", "multiprocessing"})
_TEMPFILE_MODULES: Final = frozenset({"tempfile"})
_GITHUB_MODULES: Final = frozenset({"github", "ghapi", "gidgethub", "PyGithub"})
_MODEL_MODULES: Final = frozenset(
    {
        "openai",
        "anthropic",
        "groq",
        "mistralai",
        "together",
        "cohere",
        "vertexai",
        "litellm",
        "google.generativeai",
        "google.genai",
        "langchain_openai",
        "langchain_anthropic",
    }
)
_PATHLIB_MODULES: Final = frozenset({"pathlib", "pathlib.Path"})

_OS_SUBPROCESS_ATTRS: Final = frozenset(
    {
        "system",
        "popen",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
        "fork",
        "forkpty",
        "startfile",
    }
)
_OS_WRITE_ATTRS: Final = frozenset(
    {
        "remove",
        "unlink",
        "rmdir",
        "removedirs",
        "mkdir",
        "makedirs",
        "rename",
        "renames",
        "replace",
        "chmod",
        "chown",
        "truncate",
        "symlink",
        "link",
    }
)
_PATH_WRITE_ATTRS: Final = frozenset(
    {
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "chmod",
        "symlink_to",
        "hardlink_to",
    }
)
_GENERIC_WRITE_ATTRS: Final = frozenset({"write", "writelines"})
_BUFFER_MODULES: Final = frozenset({"io.StringIO", "io.BytesIO", "StringIO", "BytesIO"})
_OPAQUE_BUILTINS: Final = frozenset({"eval", "exec", "compile", "__import__"})
_DYNAMIC_IMPORT_ATTRS: Final = frozenset({"import_module", "__import__"})

_SECRET_ENV_MARKERS: Final = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "APIKEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "ACCESS_KEY",
    "AUTH",
)
_MODEL_ENV_NAMES: Final = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "TOGETHER_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "HUGGINGFACE_API_KEY",
        "HF_TOKEN",
    }
)
_GITHUB_MUTATION_SCOPES: Final = frozenset(
    {
        "actions",
        "administration",
        "attestations",
        "checks",
        "contents",
        "deployments",
        "discussions",
        "issues",
        "packages",
        "pages",
        "pull-requests",
        "repository-projects",
        "security-events",
        "statuses",
    }
)
_WORKFLOW_NETWORK_TOKENS: Final = (
    "curl ",
    "curl\t",
    "wget ",
    "wget\t",
    "http://",
    "https://",
    "pip install",
    "npm install",
    "npx ",
    "uv pip",
)
_WORKFLOW_MODEL_TOKENS: Final = (
    "openai",
    "anthropic",
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)
_WORKFLOW_GITHUB_MUTATION_TOKENS: Final = (
    "gh pr ",
    "gh issue ",
    "gh api ",
    "gh release ",
    "gh repo ",
    "api.github.com",
)

_PERMISSIONS_LINE = "permissions"


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    """Classification of one path."""

    path: str
    kind: str
    capabilities: Mapping[str, str]
    reasons: Mapping[str, tuple[str, ...]]
    missing: bool = False

    def verdict(self, name: str) -> str:
        if name not in _CAPABILITY_SET:
            raise KeyError(f"unknown capability name: {name}")
        return self.capabilities[name]


@dataclass(frozen=True, slots=True)
class CapabilityInventory:
    """Deterministic collection of capability records."""

    schema_version: int
    records: tuple[CapabilityRecord, ...]

    def record_for(self, path: str) -> CapabilityRecord:
        normalized = _posix_relpath(path)
        for record in self.records:
            if record.path == normalized:
                return record
        raise KeyError(f"path not in inventory: {normalized}")


def _require_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _require_positive_int(value: object, name: str) -> int:
    number = _require_int(value, name)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _posix_relpath(path: str | Path) -> str:
    text = path.as_posix() if isinstance(path, Path) else str(path).replace("\\", "/")
    return text.lstrip("./") if text.startswith("./") else text


def _blank_reasons() -> dict[str, list[str]]:
    return {name: [] for name in CAPABILITY_NAMES}


def _unknown_map(reason: str) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    capabilities = {name: "unknown" for name in CAPABILITY_NAMES}
    reasons = {name: (reason,) for name in CAPABILITY_NAMES}
    return capabilities, reasons


def _finalize(
    present: set[str],
    opaque: set[str],
    reasons: Mapping[str, Sequence[str]],
    *,
    fully_classified: bool,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    capabilities: dict[str, str] = {}
    frozen_reasons: dict[str, tuple[str, ...]] = {}
    for name in CAPABILITY_NAMES:
        if name in present:
            verdict = "present"
        elif not fully_classified or name in opaque:
            verdict = "unknown"
        else:
            verdict = "absent"
        capabilities[name] = verdict
        frozen_reasons[name] = tuple(reasons[name])
        if verdict == "unknown" and not frozen_reasons[name]:
            frozen_reasons[name] = ("classification incomplete; unknown stays unknown",)
        if verdict == "absent":
            frozen_reasons[name] = ()
    return capabilities, frozen_reasons


def secret_like_path(relative: str) -> bool:
    """Return True when the relative path is itself a secret-bearing location."""

    posix = _posix_relpath(relative)
    parts = tuple(part for part in posix.split("/") if part and part != ".")
    if not parts:
        return False
    if any(part in _SECRET_DIR_PARTS for part in parts[:-1]):
        return True
    name = parts[-1]
    lowered = name.lower()
    if lowered in _SECRET_FILENAMES:
        return True
    if lowered.startswith(".env."):
        return True
    suffix = Path(lowered).suffix
    return suffix in _SECRET_SUFFIXES


def _is_workflow_path(relative: str) -> bool:
    posix = _posix_relpath(relative)
    parts = posix.split("/")
    if len(parts) >= 3 and tuple(parts[:2]) == _WORKFLOW_DIR_PARTS:
        return Path(posix).suffix.lower() in _WORKFLOW_SUFFIXES
    return False


def _kind_for(relative: str) -> str:
    posix = _posix_relpath(relative)
    if secret_like_path(posix):
        return "secret_like"
    suffix = Path(posix).suffix.lower()
    if _is_workflow_path(posix):
        return "workflow"
    if suffix in _PYTHON_SUFFIXES:
        return "python"
    return "unknown"


def _env_name_is_secret(name: str) -> bool:
    compact = name.upper().replace("-", "_")
    if compact in _MODEL_ENV_NAMES:
        return True
    return any(marker in compact for marker in _SECRET_ENV_MARKERS)


def _write_mode(mode: object) -> str | None:
    if not isinstance(mode, str):
        return None
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        return "present"
    return "absent"


def _literal_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _module_root(name: str) -> str:
    return name.split(".", 1)[0]


def _record_reason(reasons: dict[str, list[str]], name: str, reason: str) -> None:
    bucket = reasons[name]
    if reason not in bucket:
        bucket.append(reason)


class _PythonClassifier(ast.NodeVisitor):
    def __init__(self) -> None:
        self.present: set[str] = set()
        self.opaque: set[str] = set()
        self.reasons = _blank_reasons()
        self.aliases: dict[str, str] = {}
        self.file_opaque = False

    def mark(self, name: str, reason: str) -> None:
        self.present.add(name)
        _record_reason(self.reasons, name, reason)

    def mark_opaque(self, *names: str, reason: str) -> None:
        if not names:
            self.file_opaque = True
            for capability in CAPABILITY_NAMES:
                self.opaque.add(capability)
                _record_reason(self.reasons, capability, reason)
            return
        for name in names:
            self.opaque.add(name)
            _record_reason(self.reasons, name, reason)

    def _bind(self, name: str, module: str) -> None:
        self.aliases[name] = module
        self._classify_module(module)

    def _classify_module(self, module: str) -> None:
        if module in _NETWORK_MODULES or _module_root(module) in _NETWORK_MODULES:
            self.mark("network", f"imports {module}")
        if module in _SUBPROCESS_MODULES or _module_root(module) in _SUBPROCESS_MODULES:
            self.mark("subprocess", f"imports {module}")
        if module in _TEMPFILE_MODULES or _module_root(module) in _TEMPFILE_MODULES:
            self.mark("filesystem_write", f"imports {module}")
        if module in _GITHUB_MODULES or _module_root(module) in _GITHUB_MODULES:
            self.mark("github_mutation", f"imports {module}")
            self.mark("network", f"imports {module}")
        if module in _MODEL_MODULES or _module_root(module) in _MODEL_MODULES:
            self.mark("model_api", f"imports {module}")
            self.mark("network", f"imports {module}")
        if module in {"socket", "ssl"}:
            self.mark("network", f"imports {module}")

    def _resolve(self, node: ast.AST) -> str | None:
        dotted = _dotted(node)
        if dotted is None:
            return None
        head, _, rest = dotted.partition(".")
        target = self.aliases.get(head, head)
        return f"{target}.{rest}" if rest else target

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", 1)[0]
            self._bind(bound, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module:
            self.mark_opaque(reason="relative import without module is opaque")
            return
        module = node.module
        self._classify_module(module)
        for alias in node.names:
            if alias.name == "*":
                self.mark_opaque(reason=f"star import from {module} is opaque")
                continue
            bound = alias.asname or alias.name
            self._bind(bound, f"{module}.{alias.name}")
        self.generic_visit(node)

    def _receiver_name(self, node: ast.AST) -> str | None:
        resolved = self._resolve(node) or _dotted(node)
        if resolved is not None:
            return resolved
        if isinstance(node, ast.Call):
            return self._receiver_name(node.func)
        return None

    def visit_Call(self, node: ast.Call) -> None:
        dotted = self._resolve(node.func) or _dotted(node.func)
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
            dotted = self.aliases.get(name, name)
        elif isinstance(node.func, ast.Attribute):
            receiver = self._receiver_name(node.func.value)
            dotted = f"{receiver}.{node.func.attr}" if receiver else node.func.attr
        if name in _OPAQUE_BUILTINS or (dotted is not None and dotted.split(".")[-1] in _OPAQUE_BUILTINS):
            self.mark_opaque(reason=f"opaque builtin {name or dotted}")
        if dotted is not None:
            self._classify_call(dotted, node)
        self.generic_visit(node)

    def _classify_call(self, dotted: str, node: ast.Call) -> None:
        parts = dotted.split(".")
        root = parts[0]
        attr = parts[-1]
        if root in {"os"} and attr in _OS_SUBPROCESS_ATTRS:
            self.mark("subprocess", f"calls {dotted}")
        if root in {"os"} and attr in _OS_WRITE_ATTRS:
            self.mark("filesystem_write", f"calls {dotted}")
        if attr in _PATH_WRITE_ATTRS and (
            root in _PATHLIB_MODULES
            or root == "Path"
            or "pathlib" in dotted
            or dotted.startswith("Path.")
            or dotted.endswith(".Path." + attr)
            or ".Path." in dotted
        ):
            self.mark("filesystem_write", f"calls {dotted}")
        elif attr in _GENERIC_WRITE_ATTRS:
            if dotted in _BUFFER_MODULES or any(dotted.startswith(f"{name}.") for name in _BUFFER_MODULES):
                pass
            elif root in _PATHLIB_MODULES or root == "Path" or "pathlib" in dotted:
                self.mark("filesystem_write", f"calls {dotted}")
            else:
                self.mark_opaque("filesystem_write", reason=f"untyped {attr} call is opaque")
        if dotted in {"open", "builtins.open", "io.open"} or attr == "open":
            self._classify_open(node, dotted)
        if root in _SUBPROCESS_MODULES or dotted.startswith("subprocess"):
            self.mark("subprocess", f"calls {dotted}")
            self._classify_github_cli(node)
        if root in _NETWORK_MODULES or any(dotted.startswith(mod) for mod in ("urllib.request", "http.client")):
            self.mark("network", f"calls {dotted}")
        if attr in {"urlopen", "request", "get", "post", "put", "patch", "delete", "head", "options"}:
            if root in _NETWORK_MODULES or root in {"requests", "httpx", "aiohttp", "urllib"}:
                self.mark("network", f"calls {dotted}")
                self._classify_http_target(node, dotted)
        if root in {"importlib"} and attr in _DYNAMIC_IMPORT_ATTRS:
            module_name = _literal_str(node.args[0]) if node.args else None
            if module_name is None:
                self.mark_opaque(reason=f"dynamic import via {dotted}")
            else:
                self._classify_module(module_name)
        if dotted in {"getattr", "builtins.getattr"}:
            self._classify_getattr(node)
        if root in {"os"} and attr in {"getenv", "environ"}:
            self._classify_env_arg(node)
        if dotted.endswith("environ.get") or dotted.endswith("environ.__getitem__"):
            self._classify_env_arg(node)

    def _classify_open(self, node: ast.Call, dotted: str) -> None:
        mode_node: ast.AST | None = None
        if len(node.args) >= 2:
            mode_node = node.args[1]
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
        path_node = node.args[0] if node.args else None
        path_value = _literal_str(path_node) if path_node is not None else None
        if path_value and secret_like_path(path_value):
            self.mark("secret_access", f"{dotted} on secret-like path {path_value}")
        if mode_node is None:
            return
        mode = _literal_str(mode_node)
        if mode is None:
            self.mark_opaque("filesystem_write", reason=f"{dotted} uses a non-literal mode")
            return
        if _write_mode(mode) == "present":
            self.mark("filesystem_write", f"{dotted} mode {mode}")

    def _classify_getattr(self, node: ast.Call) -> None:
        if len(node.args) < 2:
            self.mark_opaque(reason="getattr with missing arguments is opaque")
            return
        target = self._resolve(node.args[0]) or _dotted(node.args[0])
        attr = _literal_str(node.args[1])
        if attr is None:
            if target is not None and _module_root(target) in {"os", "subprocess", "socket", "requests", "httpx"}:
                self.mark_opaque(
                    "subprocess",
                    "filesystem_write",
                    "network",
                    reason=f"dynamic getattr on {target}",
                )
            else:
                self.mark_opaque(reason="dynamic getattr is opaque")
            return
        if target is None:
            return
        fake = ast.Call(
            func=ast.Attribute(value=node.args[0], attr=attr, ctx=ast.Load()),
            args=list(node.args[2:]),
            keywords=[],
        )
        self._classify_call(f"{target}.{attr}", fake)

    def _classify_env_arg(self, node: ast.Call) -> None:
        if not node.args:
            self.mark_opaque("secret_access", reason="environment lookup without a literal name")
            return
        name = _literal_str(node.args[0])
        if name is None:
            self.mark_opaque("secret_access", reason="environment lookup with a non-literal name")
            return
        if name in _MODEL_ENV_NAMES:
            self.mark("secret_access", f"reads {name}")
            self.mark("model_api", f"reads {name}")
        elif _env_name_is_secret(name):
            self.mark("secret_access", f"reads {name}")

    def _classify_http_target(self, node: ast.Call, dotted: str) -> None:
        url = None
        if node.args:
            url = _literal_str(node.args[0])
        for keyword in node.keywords:
            if keyword.arg in {"url", "host"}:
                url = _literal_str(keyword.value) or url
        if url is None:
            return
        lowered = url.lower()
        if "api.github.com" in lowered:
            method = dotted.rsplit(".", 1)[-1]
            if method in {"post", "put", "patch", "delete"}:
                self.mark("github_mutation", f"{dotted} to api.github.com")
            elif method in {"get", "head", "options", "request"}:
                self.mark_opaque("github_mutation", reason=f"{dotted} to api.github.com with unspecified mutation")
        if any(token in lowered for token in ("openai.com", "anthropic.com", "googleapis.com/v1beta", "groq.com")):
            self.mark("model_api", f"{dotted} to model endpoint")

    def _classify_github_cli(self, node: ast.Call) -> None:
        if not node.args:
            return
        argv = node.args[0]
        tokens: list[str] = []
        if isinstance(argv, ast.Constant) and isinstance(argv.value, str):
            tokens = argv.value.split()
        elif isinstance(argv, (ast.List, ast.Tuple)):
            for element in argv.elts:
                value = _literal_str(element)
                if value is None:
                    tokens.append("")
                    continue
                tokens.append(value)
        if not tokens:
            return
        if tokens[0].endswith("gh") or tokens[0] == "gh":
            self.mark("github_mutation", "invokes GitHub CLI")
            self.mark("network", "invokes GitHub CLI")

    def visit_Subscript(self, node: ast.Subscript) -> None:
        target = self._resolve(node.value) or _dotted(node.value)
        key = _literal_str(node.slice)
        if target is not None and target.endswith("environ"):
            if key is None:
                self.mark_opaque("secret_access", reason="os.environ subscript is non-literal")
            elif key in _MODEL_ENV_NAMES:
                self.mark("secret_access", f"reads {key}")
                self.mark("model_api", f"reads {key}")
            elif _env_name_is_secret(key):
                self.mark("secret_access", f"reads {key}")
        self.generic_visit(node)


def _classify_python(text: str) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return _unknown_map("python syntax could not be parsed")
    classifier = _PythonClassifier()
    classifier.visit(tree)
    return _finalize(
        classifier.present,
        classifier.opaque,
        classifier.reasons,
        fully_classified=not classifier.file_opaque,
    )


def _strip_comment(value: str) -> str:
    return value.split("#", 1)[0].rstrip()


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _workflow_is_opaque(text: str) -> bool:
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("<<:"):
            return True
        if stripped[:1] in {"*", "&"}:
            return True
        if ": *" in stripped or ": &" in stripped or stripped.endswith(": *") or " * " in stripped:
            return True
    return False


def _iter_permission_scopes(lines: Sequence[str]) -> tuple[list[tuple[str, str]], bool]:
    """Return (scope, value) pairs and whether the permissions surface was fully parsed."""

    scopes: list[tuple[str, str]] = []
    parsed = True
    seen_top_level = False
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = _strip_comment(line).strip()
        if not stripped:
            index += 1
            continue
        key, sep, rest = stripped.partition(":")
        if sep and _unquote(key.strip()).lower() == _PERMISSIONS_LINE:
            seen_top_level = seen_top_level or _indent(line) == 0
            value = rest.strip()
            indent = _indent(line)
            if value:
                normalized = _unquote(value).lower()
                if normalized in {"", "{}"}:
                    index += 1
                    continue
                if normalized in {"read-all", "write-all"}:
                    scopes.append(("*", normalized))
                    index += 1
                    continue
                parsed = False
                index += 1
                continue
            cursor = index + 1
            while cursor < len(lines):
                child = lines[cursor]
                child_stripped = _strip_comment(child).strip()
                if not child_stripped:
                    cursor += 1
                    continue
                if _indent(child) <= indent:
                    break
                child_key, child_sep, child_rest = child_stripped.partition(":")
                if not child_sep:
                    parsed = False
                    cursor += 1
                    continue
                scope = _unquote(child_key.strip()).lower()
                scope_value = _unquote(child_rest.strip()).lower()
                if not scope or scope_value not in {"read", "write", "none"}:
                    parsed = False
                    cursor += 1
                    continue
                scopes.append((scope, scope_value))
                cursor += 1
            index = cursor
            continue
        index += 1
    if not seen_top_level:
        return scopes, False
    return scopes, parsed


def _classify_workflow(text: str) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    reasons = _blank_reasons()
    present: set[str] = set()
    opaque: set[str] = set()
    if _workflow_is_opaque(text):
        return _unknown_map("workflow YAML aliases/merges are opaque")

    lowered = text.lower()
    if "${{ secrets." in lowered or "secrets." in lowered:
        present.add("secret_access")
        _record_reason(reasons, "secret_access", "references GitHub secrets")

    if any(token in lowered for token in _WORKFLOW_NETWORK_TOKENS):
        present.add("network")
        _record_reason(reasons, "network", "workflow performs outbound network-shaped work")

    uses_remote = False
    uses_local_only = False
    for raw in text.splitlines():
        stripped = _strip_comment(raw).strip().lower()
        if stripped.startswith("uses:"):
            value = stripped.split(":", 1)[1].strip()
            value = _unquote(value)
            if value.startswith("./"):
                uses_local_only = True
            elif value:
                uses_remote = True
    if uses_remote:
        present.add("network")
        _record_reason(reasons, "network", "workflow uses a remote GitHub Action")
    elif uses_local_only and "network" not in present:
        opaque.add("network")
        _record_reason(reasons, "network", "local action may still perform network I/O")

    if "run:" in lowered:
        present.add("subprocess")
        _record_reason(reasons, "subprocess", "workflow has a run step")
        opaque.add("filesystem_write")
        _record_reason(reasons, "filesystem_write", "run steps may write the runner filesystem")
        if "network" not in present:
            opaque.add("network")
            _record_reason(reasons, "network", "run steps may perform network I/O")

    if "actions/checkout" in lowered:
        present.add("filesystem_write")
        _record_reason(reasons, "filesystem_write", "actions/checkout writes the workspace")
        present.add("network")
        _record_reason(reasons, "network", "actions/checkout fetches from GitHub")

    if any(token in lowered for token in _WORKFLOW_MODEL_TOKENS):
        present.add("model_api")
        present.add("network")
        _record_reason(reasons, "model_api", "workflow references a model API surface")

    if any(token in lowered for token in _WORKFLOW_GITHUB_MUTATION_TOKENS):
        present.add("github_mutation")
        present.add("network")
        _record_reason(reasons, "github_mutation", "workflow invokes a GitHub mutation surface")

    scopes, permissions_parsed = _iter_permission_scopes(text.splitlines())
    write_scopes = [
        scope
        for scope, value in scopes
        if value == "write" and (scope == "*" or scope in _GITHUB_MUTATION_SCOPES)
    ]
    if write_scopes or any(value == "write-all" for _, value in scopes):
        present.add("github_mutation")
        _record_reason(reasons, "github_mutation", "workflow grants write token permissions")
    elif not permissions_parsed:
        opaque.add("github_mutation")
        _record_reason(
            reasons,
            "github_mutation",
            "workflow permissions are missing or opaque; unknown stays unknown",
        )
    elif "secret_access" in present and "github_mutation" not in present:
        opaque.add("github_mutation")
        _record_reason(
            reasons,
            "github_mutation",
            "secrets are referenced with read-only tokens; mutation stays unknown",
        )

    fully_classified = permissions_parsed
    return _finalize(present, opaque, reasons, fully_classified=fully_classified)


def classify_text(
    relative: str,
    text: str,
    *,
    kind: str | None = None,
    missing: bool = False,
) -> CapabilityRecord:
    """Classify in-memory file text. Does not touch the network or GitHub."""

    posix = _posix_relpath(relative)
    if missing:
        capabilities, reasons = _unknown_map("path does not exist")
        return CapabilityRecord(
            path=posix,
            kind="missing",
            capabilities=capabilities,
            reasons=reasons,
            missing=True,
        )
    resolved_kind = kind or _kind_for(posix)
    if resolved_kind == "secret_like":
        capabilities, reasons = _unknown_map("secret-like path is not parsed as code")
        capabilities["secret_access"] = "present"
        reasons["secret_access"] = ("path matches a secret-bearing location",)
        return CapabilityRecord(
            path=posix,
            kind=resolved_kind,
            capabilities=capabilities,
            reasons=reasons,
        )
    if resolved_kind == "python":
        capabilities, reasons = _classify_python(text)
        return CapabilityRecord(path=posix, kind="python", capabilities=capabilities, reasons=reasons)
    if resolved_kind == "workflow":
        capabilities, reasons = _classify_workflow(text)
        return CapabilityRecord(path=posix, kind="workflow", capabilities=capabilities, reasons=reasons)
    capabilities, reasons = _unknown_map("file kind is unclassified; unknown stays unknown")
    return CapabilityRecord(path=posix, kind="unknown", capabilities=capabilities, reasons=reasons)


def classify_path(
    root: str | Path,
    relative: str | Path,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> CapabilityRecord:
    """Classify one path under ``root`` without following symlinks."""

    limit = _require_positive_int(max_file_bytes, "max_file_bytes")
    root_path = Path(root)
    posix = _posix_relpath(relative)
    candidate = Path(posix)
    if candidate.is_absolute() or ".." in candidate.parts:
        capabilities, reasons = _unknown_map("path escapes inventory root")
        return CapabilityRecord(
            path=posix,
            kind="unknown",
            capabilities=capabilities,
            reasons=reasons,
        )
    path = root_path.joinpath(*candidate.parts)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return classify_text(posix, "", missing=True)
    except OSError as exc:
        capabilities, reasons = _unknown_map(f"path metadata unread: {type(exc).__name__}")
        return CapabilityRecord(path=posix, kind="unknown", capabilities=capabilities, reasons=reasons)

    if os.path.islink(path):
        capabilities, reasons = _unknown_map("symlinks are not followed")
        return CapabilityRecord(path=posix, kind="unknown", capabilities=capabilities, reasons=reasons)
    if not os.path.isfile(path):
        capabilities, reasons = _unknown_map("path is not a regular file")
        return CapabilityRecord(path=posix, kind="unknown", capabilities=capabilities, reasons=reasons)
    if metadata.st_size > limit:
        capabilities, reasons = _unknown_map("file exceeds classification size bound")
        return CapabilityRecord(
            path=posix,
            kind=_kind_for(posix),
            capabilities=capabilities,
            reasons=reasons,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        capabilities, reasons = _unknown_map(f"file unread: {type(exc).__name__}")
        return CapabilityRecord(
            path=posix,
            kind=_kind_for(posix),
            capabilities=capabilities,
            reasons=reasons,
        )
    if "\x00" in text:
        capabilities, reasons = _unknown_map("binary file is unclassified")
        return CapabilityRecord(
            path=posix,
            kind=_kind_for(posix),
            capabilities=capabilities,
            reasons=reasons,
        )
    return classify_text(posix, text)


def _walk_files(root: Path, relative_root: str) -> list[str]:
    base = root.joinpath(*Path(_posix_relpath(relative_root)).parts) if relative_root not in {".", ""} else root
    if not base.exists():
        return []
    collected: list[str] = []
    pending = [base]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            rel = directory.relative_to(root).as_posix() if directory != root else directory.name
            collected.append(rel)
            continue
        children: list[os.DirEntry[str]] = []
        files: list[os.DirEntry[str]] = []
        for entry in entries:
            if entry.name in SKIP_DIR_NAMES:
                continue
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                children.append(entry)
            elif entry.is_file(follow_symlinks=False):
                files.append(entry)
        for entry in files:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            kind = _kind_for(relative)
            if kind in {"python", "workflow", "secret_like"}:
                collected.append(relative)
        pending.extend(Path(child.path) for child in sorted(children, key=lambda item: item.name, reverse=True))
    return collected


def inventory_paths(
    root: str | Path,
    paths: Sequence[str | Path],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> CapabilityInventory:
    """Classify an explicit path list in deterministic order."""

    _require_positive_int(max_file_bytes, "max_file_bytes")
    records = tuple(
        classify_path(root, path, max_file_bytes=max_file_bytes)
        for path in sorted({_posix_relpath(item) for item in paths})
    )
    return CapabilityInventory(schema_version=SCHEMA_VERSION, records=records)


def inventory_repository(
    root: str | Path,
    *,
    relative_roots: Sequence[str] = DEFAULT_SCAN_ROOTS,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> CapabilityInventory:
    """Inventory default module and workflow surfaces under ``root``."""

    _require_positive_int(max_file_bytes, "max_file_bytes")
    root_path = Path(root)
    discovered: set[str] = set()
    for relative_root in relative_roots:
        posix = _posix_relpath(relative_root)
        if posix == ".." or posix.startswith("../") or ".." in Path(posix).parts:
            raise ValueError("relative_roots must stay inside the inventory root")
        discovered.update(_walk_files(root_path, posix))
    return inventory_paths(root_path, sorted(discovered), max_file_bytes=max_file_bytes)


def inventory_snapshot(inventory: CapabilityInventory) -> dict[str, object]:
    """Return a JSON-ready, deterministic snapshot."""

    version = _require_int(inventory.schema_version, "schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {version}")
    present = absent = unknown = missing = 0
    records: list[dict[str, object]] = []
    for record in inventory.records:
        if record.missing:
            missing += 1
        for verdict in record.capabilities.values():
            if verdict == "present":
                present += 1
            elif verdict == "absent":
                absent += 1
            else:
                unknown += 1
        records.append(
            {
                "path": record.path,
                "kind": record.kind,
                "missing": record.missing,
                "capabilities": dict(record.capabilities),
                "reasons": {name: list(record.reasons[name]) for name in CAPABILITY_NAMES},
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "task_key": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "capability_names": list(CAPABILITY_NAMES),
        "counts": {
            "records": len(inventory.records),
            "missing": missing,
            "present": present,
            "absent": absent,
            "unknown": unknown,
        },
        "records": records,
    }


def inventory_from_mapping(payload: Mapping[str, object]) -> CapabilityInventory:
    """Rehydrate an inventory from a snapshot mapping. Fail closed on bool-as-int."""

    if not isinstance(payload, Mapping):
        raise TypeError("inventory payload must be a mapping")
    version = _require_int(payload.get("schema_version"), "schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {version}")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise TypeError("records must be a list")
    records: list[CapabilityRecord] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping):
            raise TypeError(f"records[{index}] must be a mapping")
        path = raw.get("path")
        kind = raw.get("kind")
        missing = raw.get("missing", False)
        capabilities = raw.get("capabilities")
        reasons = raw.get("reasons")
        if not isinstance(path, str) or not path:
            raise ValueError(f"records[{index}].path must be a non-empty string")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"records[{index}].kind must be a non-empty string")
        if not isinstance(missing, bool):
            raise TypeError(f"records[{index}].missing must be a bool")
        if not isinstance(capabilities, Mapping):
            raise TypeError(f"records[{index}].capabilities must be a mapping")
        if not isinstance(reasons, Mapping):
            raise TypeError(f"records[{index}].reasons must be a mapping")
        normalized: dict[str, str] = {}
        normalized_reasons: dict[str, tuple[str, ...]] = {}
        extra = set(capabilities) - _CAPABILITY_SET
        if extra:
            raise ValueError(f"records[{index}] has unknown capabilities: {sorted(extra)}")
        for name in CAPABILITY_NAMES:
            verdict = capabilities.get(name, "unknown")
            if verdict not in _VERDICT_SET:
                raise ValueError(f"records[{index}].capabilities[{name}] is not a known verdict")
            normalized[name] = str(verdict)
            reason_values = reasons.get(name, ())
            if isinstance(reason_values, str):
                raise TypeError(f"records[{index}].reasons[{name}] must be a sequence of strings")
            if not isinstance(reason_values, Sequence):
                raise TypeError(f"records[{index}].reasons[{name}] must be a sequence of strings")
            normalized_reasons[name] = tuple(str(item) for item in reason_values)
        records.append(
            CapabilityRecord(
                path=_posix_relpath(path),
                kind=kind,
                capabilities=normalized,
                reasons=normalized_reasons,
                missing=missing,
            )
        )
    records_sorted = tuple(sorted(records, key=lambda item: item.path))
    return CapabilityInventory(schema_version=version, records=records_sorted)
