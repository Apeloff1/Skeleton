"""Generated-code sandbox — deny-by-default mediation for untrusted model/tool output.

Model text, tool arguments, and generated source are data. They cannot grant,
revoke, or widen capabilities. Filesystem, network, and process effects happen
only through this mediator, and only when a trusted caller sealed matching
grants. Anything outside that grant fails closed.

The kernel capability sandbox remains the grant authority. This module adds
the generated-code/tool boundary: static inspection, scoped path/host/process
checks, and a frozen policy snapshot that untrusted input cannot mutate.
"""

from __future__ import annotations

import ast
import ipaddress
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import unquote, urlparse

from skeleton.kernel.sandbox import Capability, CapabilityDenied, Sandbox


MAX_PAYLOAD_CHARS = 32_768
MAX_OPERATIONS = 256
SANDBOX_HOLDER = "generated-code"

_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "forget your instructions",
    "you are now a different",
    "system: grant",
    "developer override",
    "jailbreak",
    "<|system|>",
    "### system",
)

_SECRET_ENV_MARKERS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "authorization",
    "aws_access",
    "aws_secret",
    "private_key",
)

_SECRET_PATH_MARKERS = (
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "secrets",
    "shadow",
    "passwd",
    ".netrc",
    "authorized_keys",
)

_FS_MODULES = frozenset({"os", "pathlib", "shutil", "tempfile", "aiofiles", "io"})
_NET_MODULES = frozenset({
    "socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "telnetlib", "webbrowser",
})
_PROC_MODULES = frozenset({
    "subprocess", "multiprocessing", "pty", "ctypes", "os",
})
_SECRET_MODULES = frozenset({"os", "keyring"})
_UNSAFE_MODULES = frozenset({
    "pickle", "marshal", "shelve", "importlib", "runpy", "code", "codeop",
    "builtins", "sys",
})

_FS_CALLS = frozenset({
    "open", "builtins.open", "__builtins__.open", "io.open", "io.FileIO", "os.open", "os.fdopen", "os.remove", "os.unlink", "os.rename", "os.replace",
    "os.mkdir", "os.makedirs", "os.rmdir", "os.removedirs", "os.listdir",
    "os.scandir", "os.walk", "os.chmod", "os.chown", "os.link", "os.symlink",
    "os.readlink", "os.truncate", "pathlib.Path", "shutil.copy", "shutil.copy2",
    "shutil.copytree", "shutil.move", "shutil.rmtree",
})
_NET_CALLS = frozenset({
    "socket.socket", "socket.create_connection", "socket.connect",
    "urllib.request.urlopen", "urllib.request.urlretrieve",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "requests.get", "requests.post", "requests.request",
    "httpx.get", "httpx.post", "httpx.request",
})
_PROC_CALLS = frozenset({
    "os.system", "os.popen", "os.execv", "os.execve", "os.execl", "os.execle",
    "os.execlp", "os.execvp", "os.execvpe", "os.spawnv", "os.spawnve",
    "os.spawnlp", "os.spawnlpe", "os.posix_spawn", "os.fork", "os.forkpty",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output",
    "multiprocessing.Process", "multiprocessing.Pool",
    "pty.spawn", "ctypes.CDLL", "ctypes.PyDLL",
})
_EVAL_CALLS = frozenset({
    "eval", "exec", "compile", "__import__",
    "builtins.eval", "builtins.exec", "builtins.compile", "builtins.__import__",
    "__builtins__.eval", "__builtins__.exec", "__builtins__.compile", "__builtins__.__import__",
})
_TRACKED_CALLABLES = frozenset().union(
    _FS_CALLS,
    _NET_CALLS,
    _PROC_CALLS,
    _EVAL_CALLS,
    {
        "getattr",
        "builtins.getattr",
        "importlib.import_module",
        "os.getenv",
        "os.environ.get",
        "os.environ.__getitem__",
        "sandbox.grant",
        "GeneratedCodeSandbox.grant",
    },
)


class SandboxCapability(str, Enum):
    """Sensitive effects generated code may request. Closed set; deny by default."""

    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PROCESS = "process"
    SECRETS = "secrets"


class OperationKind(str, Enum):
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    NETWORK = "network"
    PROCESS = "process"
    SECRET_READ = "secret.read"
    POLICY_MUTATE = "policy.mutate"
    UNSAFE_EVAL = "unsafe.eval"
    DYNAMIC_IMPORT = "dynamic.import"


class PayloadKind(str, Enum):
    PYTHON = "python"
    PROMPT = "prompt"
    TOOL_JSON = "tool-json"


@dataclass(frozen=True)
class Operation:
    kind: OperationKind
    target: str
    capability: Optional[SandboxCapability]
    detail: str = ""


@dataclass(frozen=True)
class SandboxDecision:
    allowed: bool
    reason: str
    operation: Optional[Operation] = None
    policy_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "operation": None if self.operation is None else {
                "kind": self.operation.kind.value,
                "target": self.operation.target,
                "capability": (
                    None
                    if self.operation.capability is None
                    else self.operation.capability.value
                ),
                "detail": self.operation.detail,
            },
            "policy_changed": self.policy_changed,
        }


class SandboxPolicyError(CapabilityDenied):
    code = "KRN.SANDBOX_POLICY"
    http_status = 403


class CorpusScanError(RuntimeError):
    """Raised when the adversarial corpus or scanner cannot fail closed cleanly."""


_CAPABILITY_MAP = {
    SandboxCapability.FILESYSTEM: (Capability.FS_READ, Capability.FS_WRITE),
    SandboxCapability.NETWORK: (Capability.NET_EGRESS,),
    SandboxCapability.PROCESS: (Capability.SUBPROCESS,),
    SandboxCapability.SECRETS: (Capability.SECRET_READ,),
}

def normalize_sandbox_capability(value: SandboxCapability | str | object) -> SandboxCapability:
    if isinstance(value, SandboxCapability):
        return value
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        raise TypeError("capability values must be SandboxCapability or str")
    try:
        return SandboxCapability(raw)
    except ValueError as exc:
        raise ValueError(f"unknown sandbox capability: {raw}") from exc


class GeneratedCodeSandbox:
    """Trusted mediator for generated code and untrusted tool/model payloads."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        grants: Iterable[SandboxCapability | str | object] = (),
        network_allowlist: Iterable[str] = (),
        process_allowlist: Iterable[str] = (),
        kernel: Optional[Sandbox] = None,
    ) -> None:
        root = Path(workspace_root).expanduser()
        try:
            self._root = root.resolve(strict=False)
        except OSError as exc:
            raise SandboxPolicyError(
                "workspace root is not resolvable",
                context={"workspace": str(workspace_root)},
            ) from exc
        self._kernel = kernel or Sandbox()
        self._holder = SANDBOX_HOLDER
        self._sealed = False
        self._network_allowlist = frozenset(_normalize_host(item) for item in network_allowlist)
        self._process_allowlist = frozenset(str(item) for item in process_allowlist)
        for capability in grants:
            self._grant_unlocked(normalize_sandbox_capability(capability))
        self._snapshot = self._grant_fingerprint()

    def grant(self, capability: SandboxCapability | str | object, scope: str = "*") -> None:
        if self._sealed:
            raise SandboxPolicyError(
                "sealed sandbox policy cannot be widened",
                context={"capability": str(capability), "scope": scope},
            )
        self._grant_unlocked(normalize_sandbox_capability(capability), scope)
        self._snapshot = self._grant_fingerprint()

    def seal(self) -> None:
        self._sealed = True
        self._snapshot = self._grant_fingerprint()

    @property
    def sealed(self) -> bool:
        return self._sealed

    def granted_capabilities(self) -> frozenset[SandboxCapability]:
        granted: set[SandboxCapability] = set()
        for capability, kernel_caps in _CAPABILITY_MAP.items():
            if all(self._kernel.can(self._holder, item) for item in kernel_caps):
                granted.add(capability)
        return frozenset(granted)

    def ingest_untrusted(
        self,
        payload: str,
        *,
        kind: PayloadKind | str = PayloadKind.PROMPT,
    ) -> SandboxDecision:
        """Accept untrusted text as data. Policy never changes."""
        before = self._grant_fingerprint()
        _bounded_payload(payload)
        payload_kind = PayloadKind(kind) if not isinstance(kind, PayloadKind) else kind
        try:
            operations = self.inspect(payload, kind=payload_kind)
        except SandboxPolicyError as exc:
            after = self._grant_fingerprint()
            if after != before:
                raise SandboxPolicyError(
                    "untrusted input mutated policy",
                    context={"before": before, "after": after},
                ) from exc
            return SandboxDecision(False, str(exc), policy_changed=False)
        after = self._grant_fingerprint()
        changed = after != before
        if changed:
            raise SandboxPolicyError(
                "untrusted input mutated policy",
                context={"before": before, "after": after},
            )
        denied = self._first_denied(operations)
        if denied is not None:
            return denied
        return SandboxDecision(True, "untrusted payload did not change policy", policy_changed=False)

    def inspect(self, payload: str, *, kind: PayloadKind | str = PayloadKind.PYTHON) -> tuple[Operation, ...]:
        text = _bounded_payload(payload)
        payload_kind = PayloadKind(kind) if not isinstance(kind, PayloadKind) else kind
        operations: list[Operation] = []
        if payload_kind is PayloadKind.TOOL_JSON:
            # Structured authority violations are more precise than lexical
            # widening language. Keep the exact nested key/path first so the
            # denial evidence identifies what attempted to self-grant.
            operations.extend(_inspect_tool_json(text))
            operations.extend(_injection_operations(text))
        else:
            operations.extend(_injection_operations(text))
            if payload_kind is PayloadKind.PYTHON:
                operations.extend(_inspect_python(text))
            else:
                operations.extend(_inspect_prompt(text))
        if len(operations) > MAX_OPERATIONS:
            raise SandboxPolicyError(
                "generated payload exceeds operation bound",
                context={"count": len(operations), "limit": MAX_OPERATIONS},
            )
        return tuple(operations)

    def authorize(self, operation: Operation) -> SandboxDecision:
        if operation.kind in {OperationKind.POLICY_MUTATE, OperationKind.UNSAFE_EVAL}:
            return SandboxDecision(False, "generated code cannot change policy or evaluate code", operation)
        if operation.kind is OperationKind.DYNAMIC_IMPORT:
            return SandboxDecision(False, "dynamic import is denied", operation)
        if operation.capability is None:
            return SandboxDecision(False, "operation is missing a capability", operation)
        if not self._has_capability(operation.capability):
            return SandboxDecision(
                False,
                f"missing capability {operation.capability.value}",
                operation,
            )
        if operation.kind in {OperationKind.FS_READ, OperationKind.FS_WRITE}:
            if operation.target == "<dynamic>":
                return SandboxDecision(False, "dynamic filesystem target cannot be proven contained", operation)
            try:
                resolved_path = self._contained_path(operation.target)
            except SandboxPolicyError:
                return SandboxDecision(False, "path escapes sandbox workspace", operation)
            required_kernel_cap = (
                Capability.FS_READ
                if operation.kind is OperationKind.FS_READ
                else Capability.FS_WRITE
            )
            if not self._kernel.can(self._holder, required_kernel_cap):
                return SandboxDecision(
                    False,
                    f"missing capability {required_kernel_cap.value}",
                    operation,
                )
            if (
                _looks_like_secret_path(operation.target)
                or _looks_like_secret_path(str(resolved_path))
            ) and not self._has_capability(SandboxCapability.SECRETS):
                return SandboxDecision(
                    False,
                    "secret-bearing path requires secrets capability",
                    operation,
                )
            return SandboxDecision(True, "filesystem grant covers workspace path", operation)
        if operation.kind is OperationKind.NETWORK:
            if not self._network_allowed(operation.target):
                return SandboxDecision(False, "network target is outside the grant", operation)
            return SandboxDecision(True, "network grant covers host", operation)
        if operation.kind is OperationKind.PROCESS:
            if not self._process_allowed(operation.target, operation.detail):
                return SandboxDecision(False, "process target is outside the grant", operation)
            return SandboxDecision(True, "process grant covers executable", operation)
        if operation.kind is OperationKind.SECRET_READ:
            if not self._has_capability(SandboxCapability.SECRETS):
                return SandboxDecision(False, "missing capability secrets", operation)
            return SandboxDecision(True, "secrets grant covers explicit read", operation)
        return SandboxDecision(False, "unknown operation fails closed", operation)

    def attempt(self, operation: Operation) -> str:
        decision = self.authorize(operation)
        if not decision.allowed:
            raise SandboxPolicyError(
                decision.reason,
                context={
                    "kind": operation.kind.value,
                    "target": operation.target,
                    "capability": None if operation.capability is None else operation.capability.value,
                },
            )
        if operation.kind is OperationKind.FS_READ:
            path = self._contained_path(operation.target)
            return path.read_text(encoding="utf-8")
        if operation.kind is OperationKind.FS_WRITE:
            path = self._contained_path(operation.target)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(operation.detail, encoding="utf-8")
            return "written"
        # Network and process grants never open sockets or spawn processes here.
        # Authorization is the fail-closed boundary; effects stay mediated.
        if operation.kind is OperationKind.NETWORK:
            return f"authorized-network:{operation.target}"
        if operation.kind is OperationKind.PROCESS:
            return f"authorized-process:{operation.target}"
        if operation.kind is OperationKind.SECRET_READ:
            return "authorized-secret-read"
        raise SandboxPolicyError("operation cannot be executed", context={"kind": operation.kind.value})

    def admit(self, payload: str, *, kind: PayloadKind | str = PayloadKind.PYTHON) -> SandboxDecision:
        before = self._grant_fingerprint()
        try:
            operations = self.inspect(payload, kind=kind)
        except SandboxPolicyError as exc:
            self._assert_policy_frozen(before)
            return SandboxDecision(False, str(exc), policy_changed=False)
        self._assert_policy_frozen(before)
        denied = self._first_denied(operations)
        if denied is not None:
            return denied
        return SandboxDecision(True, "payload is within sealed grants", policy_changed=False)

    def _grant_unlocked(self, capability: SandboxCapability, scope: str = "*") -> None:
        for kernel_cap in _CAPABILITY_MAP[capability]:
            self._kernel.grant(self._holder, kernel_cap, scope=scope)

    def _has_capability(self, capability: SandboxCapability) -> bool:
        return any(self._kernel.can(self._holder, item) for item in _CAPABILITY_MAP[capability])

    def _grant_fingerprint(self) -> tuple[tuple[str, str, str], ...]:
        records = []
        for grant in self._kernel.grants_for(self._holder):
            records.append((grant.holder, grant.capability.value, grant.scope))
        return tuple(sorted(records))

    def _assert_policy_frozen(self, before: tuple[tuple[str, str, str], ...]) -> None:
        after = self._grant_fingerprint()
        if after != before or after != self._snapshot:
            raise SandboxPolicyError(
                "sandbox policy changed while evaluating untrusted input",
                context={"before": before, "after": after, "sealed": self._snapshot},
            )

    def _first_denied(self, operations: tuple[Operation, ...]) -> Optional[SandboxDecision]:
        for operation in operations:
            decision = self.authorize(operation)
            if not decision.allowed:
                return decision
        return None

    def _path_allowed(self, target: str) -> bool:
        try:
            self._contained_path(target)
        except SandboxPolicyError:
            return False
        return True

    def _contained_path(self, target: str) -> Path:
        if not isinstance(target, str) or not target or "\x00" in target:
            raise SandboxPolicyError("filesystem target is invalid", context={"target": repr(target)})
        decoded = unquote(target)
        candidate = Path(decoded)
        if candidate.is_absolute():
            resolved = candidate
        else:
            resolved = self._root.joinpath(candidate)
        try:
            resolved = resolved.resolve(strict=False)
            resolved.relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise SandboxPolicyError(
                "path escapes sandbox workspace",
                context={"target": target, "workspace": str(self._root)},
            ) from exc
        return resolved

    def _network_allowed(self, target: str) -> bool:
        host = _network_host(target)
        if host is None:
            return False
        if _is_blocked_host(host):
            return False
        if self._network_allowlist and host not in self._network_allowlist:
            return False
        if self._network_allowlist:
            return True
        # A bare network grant without an explicit host allowlist still fails closed.
        return False

    def _process_allowed(self, target: str, detail: str) -> bool:
        if not target or _has_shell_metacharacters(target) or _has_shell_metacharacters(detail):
            return False
        if "shell=True" in detail:
            return False
        if not self._process_allowlist:
            return False
        return target in self._process_allowlist


def _bounded_payload(payload: object) -> str:
    if not isinstance(payload, str):
        raise SandboxPolicyError("payload must be text", context={"type": type(payload).__name__})
    if len(payload) > MAX_PAYLOAD_CHARS:
        raise SandboxPolicyError(
            "payload exceeds bound",
            context={"length": len(payload), "limit": MAX_PAYLOAD_CHARS},
        )
    return payload


def _injection_operations(text: str) -> list[Operation]:
    lowered = text.lower()
    operations: list[Operation] = []
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            operations.append(
                Operation(OperationKind.POLICY_MUTATE, marker, None, "prompt-injection marker")
            )
    if "capabilities" in lowered and any(
        token in lowered for token in ("grant", "allow", "enable", "widen", "sudo", "root")
    ):
        operations.append(
            Operation(OperationKind.POLICY_MUTATE, "capability-widening", None, "policy widening language")
        )
    return operations


def _inspect_python(source: str) -> list[Operation]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SandboxPolicyError(
            "generated code failed to parse",
            context={"lineno": exc.lineno, "msg": exc.msg},
        ) from exc
    operations: list[Operation] = []
    aliases: dict[str, str] = {}
    nodes = list(ast.walk(tree))

    # Resolve imports before inspecting calls so source ordering cannot hide a
    # sensitive callable behind an alias used earlier in the AST traversal.
    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".", 1)[0]] = item.name
                operations.extend(_import_operations(item.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                aliases[module.split(".", 1)[0]] = module
            operations.extend(_import_operations(module))
            for item in node.names:
                full_name = f"{module}.{item.name}" if module else item.name
                aliases[item.asname or item.name] = full_name
                operations.extend(_import_operations(full_name))

    aliases.update(_stable_callable_aliases(nodes, aliases))

    for node in nodes:
        if isinstance(node, ast.Call):
            operations.extend(_call_operations(node, aliases))
        elif isinstance(node, ast.Attribute):
            name = _dotted_name(node, aliases)
            if name in {"os.environ", "os.environb"}:
                operations.append(
                    Operation(
                        OperationKind.SECRET_READ,
                        name,
                        SandboxCapability.SECRETS,
                        "environment access",
                    )
                )
    return operations


def _stable_callable_aliases(
    nodes: Iterable[ast.AST],
    import_aliases: Mapping[str, str],
) -> dict[str, str]:
    """Conservatively resolve local aliases to sensitive callables, including chains."""
    node_list = list(nodes)
    resolved: dict[str, str] = {}

    changed = True
    while changed:
        changed = False
        aliases = {**import_aliases, **resolved}
        for node in node_list:
            value: ast.AST | None = None
            names: list[str] = []
            if isinstance(node, ast.Assign):
                value = node.value
                names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                value = node.value
                names = [node.target.id]
            elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                value = node.value
                names = [node.target.id]
            if value is None or not names:
                continue
            source = _dotted_name(value, aliases)
            if source not in _TRACKED_CALLABLES:
                continue
            for name in names:
                # Generated code is adversarial: once a local name is observed
                # aliasing a sensitive callable, later reassignment must not be
                # allowed to erase that provenance and create a bypass.
                if name in resolved:
                    continue
                resolved[name] = source
                changed = True
    return resolved


def _inspect_tool_json(text: str) -> list[Operation]:
    try:
        payload = json.loads(text, object_pairs_hook=_json_object_no_duplicates)
    except (json.JSONDecodeError, RecursionError) as exc:
        message = exc.msg if isinstance(exc, json.JSONDecodeError) else "nesting too deep"
        raise SandboxPolicyError(
            "tool payload failed to parse",
            context={"msg": message},
        ) from exc
    if not isinstance(payload, Mapping):
        raise SandboxPolicyError("tool payload must be an object")
    operations: list[Operation] = []
    policy_path = _nested_policy_key(payload)
    if policy_path is not None:
        operations.append(
            Operation(
                OperationKind.POLICY_MUTATE,
                policy_path,
                None,
                "tool payload attempted policy mutation",
            )
        )
    arguments = payload.get("arguments", payload)
    blob = json.dumps(arguments, sort_keys=True) if isinstance(arguments, Mapping) else str(arguments)
    operations.extend(_text_effect_operations(blob))
    name = payload.get("name") or payload.get("tool")
    if isinstance(name, str) and name.lower() in {"shell", "bash", "subprocess", "os.system"}:
        operations.append(
            Operation(OperationKind.PROCESS, name, SandboxCapability.PROCESS, "sensitive tool name")
        )
    return operations


def _json_object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise SandboxPolicyError(
                "tool payload contains duplicate JSON keys",
                context={"key": key},
            )
        payload[key] = value
    return payload


def _nested_policy_key(payload: object) -> Optional[str]:
    """Return the first nested policy/grant key, while bounding JSON traversal."""
    sensitive = frozenset(
        {
            "capability",
            "capabilities",
            "grant",
            "grants",
            "permission",
            "permissions",
            "policy",
            "scope",
            "scopes",
        }
    )
    stack: list[tuple[str, object]] = [("$", payload)]
    visits = 0
    limit = MAX_OPERATIONS * 8
    while stack:
        path, value = stack.pop()
        visits += 1
        if visits > limit:
            raise SandboxPolicyError(
                "tool payload structure exceeds bound",
                context={"visits": visits, "limit": limit},
            )
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}"
                if key_text.strip().lower() in sensitive:
                    return child_path
                stack.append((child_path, child))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                stack.append((f"{path}[{index}]", child))
    return None


def _inspect_prompt(text: str) -> list[Operation]:
    return _text_effect_operations(text)


def _text_effect_operations(text: str) -> list[Operation]:
    operations: list[Operation] = []
    lowered = text.lower()
    if any(token in lowered for token in ("../", "..\\", "/etc/", "c:\\windows", "%2e%2e")):
        operations.append(
            Operation(OperationKind.FS_READ, text.strip()[:120], SandboxCapability.FILESYSTEM, "path escape")
        )
    if any(token in lowered for token in ("http://", "https://", "ftp://", "file://", "169.254.169.254")):
        operations.append(
            Operation(OperationKind.NETWORK, text.strip()[:120], SandboxCapability.NETWORK, "network pivot")
        )
    if any(token in lowered for token in ("subprocess", "os.system", "popen(", "shell=true", "/bin/sh")):
        operations.append(
            Operation(
                OperationKind.PROCESS,
                text.strip()[:120],
                SandboxCapability.PROCESS,
                "unsafe process",
            )
        )
    if any(marker in lowered for marker in _SECRET_ENV_MARKERS):
        operations.append(
            Operation(
                OperationKind.SECRET_READ,
                text.strip()[:120],
                SandboxCapability.SECRETS,
                "secret exfil",
            )
        )
    return operations


def _import_operations(name: str) -> list[Operation]:
    root = name.split(".", 1)[0]
    operations: list[Operation] = []
    if root in _UNSAFE_MODULES or name in {"builtins.eval", "builtins.exec"}:
        operations.append(Operation(OperationKind.UNSAFE_EVAL, name, None, "unsafe module"))
    if root in _FS_MODULES:
        operations.append(
            Operation(
                OperationKind.FS_READ,
                name,
                SandboxCapability.FILESYSTEM,
                "filesystem import",
            )
        )
    if root in _NET_MODULES:
        operations.append(Operation(OperationKind.NETWORK, name, SandboxCapability.NETWORK, "network import"))
    process_import = (
        root in {"subprocess", "multiprocessing", "pty", "ctypes"}
        or (
            root == "os"
            and name.split(".")[-1]
            in {"system", "popen", "execv", "execve", "fork", "spawnv", "posix_spawn"}
        )
    )
    if process_import:
        operations.append(
            Operation(
                OperationKind.PROCESS,
                name,
                SandboxCapability.PROCESS,
                "process-sensitive import",
            )
        )
    if root in _SECRET_MODULES and "environ" in name:
        operations.append(
            Operation(
                OperationKind.SECRET_READ,
                name,
                SandboxCapability.SECRETS,
                "secret import",
            )
        )
    return operations


def _call_operations(node: ast.Call, aliases: Mapping[str, str]) -> list[Operation]:
    name = _dotted_name(node.func, aliases)
    if name.endswith(".__call__"):
        base_name = name[: -len(".__call__")]
        if base_name in _TRACKED_CALLABLES:
            name = base_name
    operations: list[Operation] = []
    for argument in (*node.args, *(item.value for item in node.keywords)):
        reference = _sensitive_callable_reference(argument, aliases)
        if reference is not None:
            operations.append(reference)
    if not name or name == "<dynamic>":
        operations.append(
            Operation(
                OperationKind.UNSAFE_EVAL,
                "<dynamic-callable>",
                None,
                "callable provenance cannot be proven",
            )
        )
        return operations
    if name in _EVAL_CALLS or name in {"getattr", "builtins.getattr"}:
        operations.append(Operation(OperationKind.UNSAFE_EVAL, name or "<dynamic>", None, "eval/getattr"))
        return operations
    if name in {"__import__", "importlib.import_module"}:
        operations.append(Operation(OperationKind.DYNAMIC_IMPORT, name, None, "dynamic import"))
        return operations
    if name in _FS_CALLS or name == "open":
        target = _literal_arg(node, 0, "file") or _literal_arg(node, 0, "path") or "<dynamic>"
        mode = _literal_arg(node, 1, "mode") or "r"
        kind = OperationKind.FS_WRITE if any(flag in mode for flag in "wax+") else OperationKind.FS_READ
        operations.append(Operation(kind, target, SandboxCapability.FILESYSTEM, f"mode={mode}"))
        if target == "<dynamic>":
            operations.append(
                Operation(
                    OperationKind.FS_WRITE,
                    target,
                    SandboxCapability.FILESYSTEM,
                    "dynamic path",
                )
            )
    if name in _NET_CALLS:
        target = _literal_arg(node, 0, "url") or _literal_arg(node, 0, "host") or "<dynamic>"
        operations.append(Operation(OperationKind.NETWORK, target, SandboxCapability.NETWORK, name))
    if name in _PROC_CALLS:
        target = _literal_arg(node, 0, "args") or _literal_arg(node, 0, "cmd") or "<dynamic>"
        detail = "shell=True" if _keyword_true(node, "shell") else name
        operations.append(Operation(OperationKind.PROCESS, str(target), SandboxCapability.PROCESS, detail))
    if name in {"os.getenv", "os.environ.get", "os.environ.__getitem__"}:
        target = _literal_arg(node, 0, "key") or "<dynamic>"
        operations.append(Operation(OperationKind.SECRET_READ, target, SandboxCapability.SECRETS, name))
    if name in {"sandbox.grant", "GeneratedCodeSandbox.grant"}:
        operations.append(Operation(OperationKind.POLICY_MUTATE, name, None, "grant call"))
    return operations


def _sensitive_callable_reference(
    node: ast.AST,
    aliases: Mapping[str, str],
) -> Optional[Operation]:
    """Fail closed when a sensitive callable is handed to higher-order code."""
    name = _dotted_name(node, aliases)
    if name in _FS_CALLS:
        return Operation(
            OperationKind.FS_READ,
            "<dynamic>",
            SandboxCapability.FILESYSTEM,
            f"sensitive callable reference: {name}",
        )
    if name in _NET_CALLS:
        return Operation(
            OperationKind.NETWORK,
            "<dynamic>",
            SandboxCapability.NETWORK,
            f"sensitive callable reference: {name}",
        )
    if name in _PROC_CALLS:
        return Operation(
            OperationKind.PROCESS,
            "<dynamic>",
            SandboxCapability.PROCESS,
            f"sensitive callable reference: {name}",
        )
    if name in _EVAL_CALLS or name in {
        "getattr",
        "builtins.getattr",
        "importlib.import_module",
        "sandbox.grant",
        "GeneratedCodeSandbox.grant",
    }:
        return Operation(
            OperationKind.UNSAFE_EVAL,
            name or "<dynamic>",
            None,
            "sensitive callable reference",
        )
    if name in {"os.getenv", "os.environ.get", "os.environ.__getitem__"}:
        return Operation(
            OperationKind.SECRET_READ,
            "<dynamic>",
            SandboxCapability.SECRETS,
            f"sensitive callable reference: {name}",
        )
    return None


def _dotted_name(node: ast.AST, aliases: Mapping[str, str]) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(aliases.get(current.id, current.id))
        return ".".join(reversed(parts))
    if isinstance(current, ast.Call) and _dotted_name(current.func, aliases) == "getattr":
        return "<dynamic>"
    return parts[-1] if parts else ""


def _literal_arg(node: ast.Call, index: int, keyword: str) -> Optional[str]:
    for item in node.keywords:
        if item.arg == keyword:
            return _literal_str(item.value)
    if len(node.args) > index:
        return _literal_str(node.args[index])
    return None


def _literal_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        chunks: list[str] = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                chunks.append(part.value)
            else:
                return None
        return "".join(chunks)
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        first = _literal_str(node.elts[0])
        return first
    return None


def _keyword_true(node: ast.Call, name: str) -> bool:
    for item in node.keywords:
        if item.arg == name and isinstance(item.value, ast.Constant) and item.value.value is True:
            return True
    return False


def _looks_like_secret_path(target: str) -> bool:
    lowered = target.lower()
    return any(marker in lowered for marker in _SECRET_PATH_MARKERS)


def _has_shell_metacharacters(value: str) -> bool:
    return any(char in value for char in (";", "|", "&", "`", "$", "(", ")", "<", ">", "\n", "\r"))


def _normalize_host(value: str) -> str:
    return value.strip().lower().rstrip(".")


def _network_host(target: str) -> Optional[str]:
    text = target.strip()
    if not text or text == "<dynamic>":
        return None
    parsed = urlparse(text if "://" in text else f"//{text}", scheme="https")
    host = parsed.hostname
    if host is None:
        host = text.split("/", 1)[0].split(":", 1)[0]
    if not host:
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    return _normalize_host(host)


def _is_blocked_host(host: str) -> bool:
    if host in {"localhost", "metadata.google.internal", "metadata"}:
        return True
    if host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.startswith("169.254.")
    return not bool(
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not getattr(address, "is_site_local", False)
    )
