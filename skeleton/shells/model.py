"""Canonical data model for the shell execution plane.

Objects here are immutable, serializable, and do not carry executable paths.
They are safe building blocks for planning, admission, audit, and orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,128}$")
_CORRELATION_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{0,160}$")
_MAX_METADATA_ITEMS = 64
_MAX_METADATA_VALUE_CHARS = 2048


class ShellModelError(ValueError):
    """Raised when a shell-plane model object is structurally invalid."""


class ExecutionClass(str, Enum):
    PROBE = "probe"
    BUILD = "build"
    TEST = "test"
    ANALYSIS = "analysis"
    FORMAT = "format"
    GENERATE = "generate"
    PACKAGE = "package"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"


class StreamDisposition(str, Enum):
    CAPTURE = "capture"
    DISCARD = "discard"


class Outcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMITED = "output_limited"
    DENIED = "denied"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


def _validate_name(label: str, value: str) -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ShellModelError(f"{label} has invalid syntax")
    return value


def _validate_tags(tags: Iterable[str]) -> frozenset[str]:
    frozen = frozenset(tags)
    if len(frozen) > 64:
        raise ShellModelError("too many tags")
    for tag in frozen:
        if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
            raise ShellModelError("invalid tag")
    return frozen


def _json_safe_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if len(metadata) > _MAX_METADATA_ITEMS:
        raise ShellModelError("too many metadata fields")
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not _NAME_RE.fullmatch(key):
            raise ShellModelError("invalid metadata key")
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and len(value) > _MAX_METADATA_VALUE_CHARS:
                raise ShellModelError("metadata value too large")
            clean[key] = value
        elif isinstance(value, (list, tuple)):
            if len(value) > 64:
                raise ShellModelError("metadata sequence too large")
            if not all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                raise ShellModelError("metadata sequence must contain scalar values")
            clean[key] = tuple(value)
        else:
            raise ShellModelError("metadata values must be JSON scalar values or scalar sequences")
    return clean


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_payload(payload: Mapping[str, Any], *, prefix: str = "sha256") -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


@dataclass(frozen=True, order=True)
class CommandIdentity:
    namespace: str
    name: str
    version: str = "1"

    def __post_init__(self) -> None:
        _validate_name("namespace", self.namespace)
        _validate_name("name", self.name)
        if not isinstance(self.version, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}", self.version):
            raise ShellModelError("invalid command version")

    @property
    def key(self) -> str:
        return f"{self.namespace}:{self.name}@{self.version}"

    @classmethod
    def parse(cls, value: str) -> "CommandIdentity":
        if not isinstance(value, str) or value.count(":") != 1 or value.count("@") != 1:
            raise ShellModelError("command identity must be namespace:name@version")
        namespace, remainder = value.split(":", 1)
        name, version = remainder.rsplit("@", 1)
        return cls(namespace=namespace, name=name, version=version)


@dataclass(frozen=True)
class CommandIntent:
    execution_class: ExecutionClass = ExecutionClass.CUSTOM
    correlation_id: str = ""
    actor: str = "unknown"
    reason: str = ""
    tags: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.execution_class, ExecutionClass):
            object.__setattr__(self, "execution_class", ExecutionClass(self.execution_class))
        if not isinstance(self.correlation_id, str) or not _CORRELATION_RE.fullmatch(self.correlation_id):
            raise ShellModelError("invalid correlation_id")
        _validate_name("actor", self.actor)
        if not isinstance(self.reason, str) or len(self.reason) > 2048:
            raise ShellModelError("reason must be a string of at most 2048 characters")
        object.__setattr__(self, "tags", _validate_tags(self.tags))
        object.__setattr__(self, "metadata", MappingProxyType(_json_safe_metadata(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_class": self.execution_class.value,
            "correlation_id": self.correlation_id,
            "actor": self.actor,
            "reason": self.reason,
            "tags": sorted(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResourceRequest:
    timeout_seconds: float | None = None
    max_output_bytes: int | None = None
    max_input_bytes: int | None = None
    cpu_weight: int = 1
    concurrency_weight: int = 1

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
        ):
            raise ShellModelError("timeout_seconds must be a positive number")
        if self.max_output_bytes is not None and (
            isinstance(self.max_output_bytes, bool)
            or not isinstance(self.max_output_bytes, int)
            or self.max_output_bytes <= 0
        ):
            raise ShellModelError("max_output_bytes must be a positive integer")
        if self.max_input_bytes is not None and (
            isinstance(self.max_input_bytes, bool)
            or not isinstance(self.max_input_bytes, int)
            or self.max_input_bytes < 0
        ):
            raise ShellModelError("max_input_bytes must be a non-negative integer")
        if isinstance(self.cpu_weight, bool) or not isinstance(self.cpu_weight, int) or self.cpu_weight <= 0 or self.cpu_weight > 1024:
            raise ShellModelError("cpu_weight outside supported bounds")
        if isinstance(self.concurrency_weight, bool) or not isinstance(self.concurrency_weight, int) or self.concurrency_weight <= 0 or self.concurrency_weight > 1024:
            raise ShellModelError("concurrency_weight outside supported bounds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_input_bytes": self.max_input_bytes,
            "cpu_weight": self.cpu_weight,
            "concurrency_weight": self.concurrency_weight,
        }


@dataclass(frozen=True)
class ShellInvocation:
    identity: CommandIdentity
    arguments: tuple[str, ...] = ()
    cwd: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    stdin: bytes | None = None
    resources: ResourceRequest = field(default_factory=ResourceRequest)
    intent: CommandIntent = field(default_factory=CommandIntent)
    allowed_returncodes: frozenset[int] = frozenset({0})
    stdout: StreamDisposition = StreamDisposition.CAPTURE
    stderr: StreamDisposition = StreamDisposition.CAPTURE

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CommandIdentity):
            raise ShellModelError("identity must be a CommandIdentity")
        args = tuple(self.arguments)
        if len(args) > 4096:
            raise ShellModelError("argument vector is structurally too large")
        for arg in args:
            if not isinstance(arg, str):
                raise ShellModelError("arguments must be strings")
            if "\x00" in arg:
                raise ShellModelError("arguments may not contain NUL")
        object.__setattr__(self, "arguments", args)

        if self.cwd is not None and (not isinstance(self.cwd, str) or "\x00" in self.cwd or len(self.cwd) > 4096):
            raise ShellModelError("invalid cwd")

        env = dict(self.environment)
        if len(env) > 512:
            raise ShellModelError("environment has too many keys")
        for key, value in env.items():
            if not isinstance(key, str) or not _ENV_RE.fullmatch(key):
                raise ShellModelError("invalid environment key")
            if not isinstance(value, str) or "\x00" in value:
                raise ShellModelError("environment values must be NUL-free strings")
        object.__setattr__(self, "environment", MappingProxyType(env))

        if self.stdin is not None and not isinstance(self.stdin, bytes):
            raise ShellModelError("stdin must be bytes")
        if not isinstance(self.resources, ResourceRequest):
            raise ShellModelError("resources must be a ResourceRequest")
        if not isinstance(self.intent, CommandIntent):
            raise ShellModelError("intent must be a CommandIntent")

        returncodes = frozenset(self.allowed_returncodes)
        if not returncodes:
            raise ShellModelError("allowed_returncodes may not be empty")
        if len(returncodes) > 64 or any(not isinstance(code, int) or code < -255 or code > 255 for code in returncodes):
            raise ShellModelError("invalid allowed return code set")
        object.__setattr__(self, "allowed_returncodes", returncodes)

        if not isinstance(self.stdout, StreamDisposition):
            object.__setattr__(self, "stdout", StreamDisposition(self.stdout))
        if not isinstance(self.stderr, StreamDisposition):
            object.__setattr__(self, "stderr", StreamDisposition(self.stderr))

    def with_intent(self, **updates: Any) -> "ShellInvocation":
        return replace(self, intent=replace(self.intent, **updates))

    def public_shape(self) -> dict[str, Any]:
        """Return a deterministic, secret-minimized identity shape.

        Argument, environment, stdin, reason, and metadata values are represented
        by byte counts/digests rather than raw values.  The shape can therefore be
        persisted in receipts without becoming a second credential store.
        """

        argument_shape = [
            {
                "bytes": len(value.encode("utf-8")),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            }
            for value in self.arguments
        ]
        env_shape = {
            key: {
                "bytes": len(value.encode("utf-8")),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            }
            for key, value in sorted(self.environment.items())
        }
        stdin_shape: dict[str, Any] | None = None
        if self.stdin is not None:
            stdin_shape = {
                "bytes": len(self.stdin),
                "sha256": hashlib.sha256(self.stdin).hexdigest(),
            }
        reason_bytes = self.intent.reason.encode("utf-8")
        metadata_json = canonical_json(dict(self.intent.metadata)).encode("utf-8")
        intent_shape = {
            "execution_class": self.intent.execution_class.value,
            "correlation_id": self.intent.correlation_id,
            "actor": self.intent.actor,
            "tags": sorted(self.intent.tags),
            "reason": {
                "bytes": len(reason_bytes),
                "sha256": hashlib.sha256(reason_bytes).hexdigest(),
            },
            "metadata": {
                "bytes": len(metadata_json),
                "sha256": hashlib.sha256(metadata_json).hexdigest(),
            },
        }
        return {
            "identity": self.identity.key,
            "argument_count": len(self.arguments),
            "arguments": argument_shape,
            "cwd": self.cwd,
            "environment": env_shape,
            "stdin": stdin_shape,
            "resources": self.resources.to_dict(),
            "intent": intent_shape,
            "allowed_returncodes": sorted(self.allowed_returncodes),
            "stdout": self.stdout.value,
            "stderr": self.stderr.value,
        }

    @property
    def fingerprint(self) -> str:
        return digest_payload(self.public_shape())


@dataclass(frozen=True)
class ExecutionTiming:
    queued_seconds: float = 0.0
    runtime_seconds: float = 0.0
    total_seconds: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.queued_seconds, self.runtime_seconds, self.total_seconds):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ShellModelError("timing values must be finite non-negative numbers")

    def to_dict(self) -> dict[str, float]:
        return {
            "queued_seconds": self.queued_seconds,
            "runtime_seconds": self.runtime_seconds,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True)
class ExecutionSummary:
    invocation_fingerprint: str
    command: str
    outcome: Outcome
    returncode: int | None = None
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    attempt_count: int = 1
    timing: ExecutionTiming = field(default_factory=ExecutionTiming)
    receipt_id: str = ""
    denial_code: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.invocation_fingerprint, str) or len(self.invocation_fingerprint) > 160:
            raise ShellModelError("invalid invocation fingerprint")
        if not isinstance(self.command, str) or len(self.command) > 256:
            raise ShellModelError("invalid command")
        if not isinstance(self.outcome, Outcome):
            object.__setattr__(self, "outcome", Outcome(self.outcome))
        if self.stdout_bytes < 0 or self.stderr_bytes < 0:
            raise ShellModelError("stream byte counts may not be negative")
        if self.attempt_count <= 0:
            raise ShellModelError("attempt_count must be positive")
        if self.denial_code and not _TAG_RE.fullmatch(self.denial_code):
            raise ShellModelError("invalid denial_code")

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.SUCCEEDED

    def to_dict(self) -> dict[str, Any]:
        return {
            "invocation_fingerprint": self.invocation_fingerprint,
            "command": self.command,
            "outcome": self.outcome.value,
            "returncode": self.returncode,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "attempt_count": self.attempt_count,
            "timing": self.timing.to_dict(),
            "receipt_id": self.receipt_id,
            "denial_code": self.denial_code,
        }


def invocation_from_dict(payload: Mapping[str, Any]) -> ShellInvocation:
    if not isinstance(payload, Mapping):
        raise ShellModelError("invocation payload must be an object")
    allowed_fields = {
        "command", "arguments", "cwd", "environment", "resources", "intent",
        "allowed_returncodes", "stdout", "stderr", "stdin",
    }
    unknown = sorted(str(key) for key in payload if key not in allowed_fields)
    if unknown:
        raise ShellModelError(f"unknown invocation field: {unknown[0]}")
    command_value = payload.get("command", "")
    if not isinstance(command_value, str):
        raise ShellModelError("command must be a string identity")
    identity = CommandIdentity.parse(command_value)

    args = payload.get("arguments", ())
    if not isinstance(args, Sequence) or isinstance(args, (str, bytes, bytearray)):
        raise ShellModelError("arguments must be a sequence")
    if any(not isinstance(item, str) for item in args):
        raise ShellModelError("every argument must be a string")

    env = payload.get("environment", {})
    if not isinstance(env, Mapping):
        raise ShellModelError("environment must be an object")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in env.items()):
        raise ShellModelError("environment must map string keys to string values")

    resources_payload = payload.get("resources", {})
    if not isinstance(resources_payload, Mapping):
        raise ShellModelError("resources must be an object")
    resource_fields = {
        "timeout_seconds", "max_output_bytes", "max_input_bytes",
        "cpu_weight", "concurrency_weight",
    }
    unknown_resources = sorted(str(key) for key in resources_payload if key not in resource_fields)
    if unknown_resources:
        raise ShellModelError(f"unknown resource field: {unknown_resources[0]}")
    resources = ResourceRequest(
        timeout_seconds=resources_payload.get("timeout_seconds"),
        max_output_bytes=resources_payload.get("max_output_bytes"),
        max_input_bytes=resources_payload.get("max_input_bytes"),
        cpu_weight=resources_payload.get("cpu_weight", 1),
        concurrency_weight=resources_payload.get("concurrency_weight", 1),
    )

    intent_payload = payload.get("intent", {})
    if not isinstance(intent_payload, Mapping):
        raise ShellModelError("intent must be an object")
    intent_fields = {"execution_class", "correlation_id", "actor", "reason", "tags", "metadata"}
    unknown_intent = sorted(str(key) for key in intent_payload if key not in intent_fields)
    if unknown_intent:
        raise ShellModelError(f"unknown intent field: {unknown_intent[0]}")
    for field_name in ("correlation_id", "actor", "reason"):
        if field_name in intent_payload and not isinstance(intent_payload[field_name], str):
            raise ShellModelError(f"intent {field_name} must be a string")
    tags = intent_payload.get("tags", ())
    if not isinstance(tags, (list, tuple, set, frozenset)) or any(not isinstance(tag, str) for tag in tags):
        raise ShellModelError("intent tags must be a string sequence")
    metadata = intent_payload.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise ShellModelError("intent metadata must be an object")
    intent = CommandIntent(
        execution_class=ExecutionClass(intent_payload.get("execution_class", "custom")),
        correlation_id=intent_payload.get("correlation_id", ""),
        actor=intent_payload.get("actor", "unknown"),
        reason=intent_payload.get("reason", ""),
        tags=frozenset(tags),
        metadata=metadata,
    )

    if payload.get("stdin") is not None:
        raise ShellModelError("raw stdin is not accepted by JSON invocation parsing")

    returncodes = payload.get("allowed_returncodes", (0,))
    if not isinstance(returncodes, (list, tuple, set, frozenset)):
        raise ShellModelError("allowed_returncodes must be an integer sequence")
    if any(isinstance(code, bool) or not isinstance(code, int) for code in returncodes):
        raise ShellModelError("allowed_returncodes must contain integers")

    cwd = payload.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ShellModelError("cwd must be a string")

    return ShellInvocation(
        identity=identity,
        arguments=tuple(args),
        cwd=cwd,
        environment=dict(env),
        resources=resources,
        intent=intent,
        allowed_returncodes=frozenset(returncodes),
        stdout=StreamDisposition(payload.get("stdout", "capture")),
        stderr=StreamDisposition(payload.get("stderr", "capture")),
    )
