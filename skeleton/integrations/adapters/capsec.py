"""Capability-security (capsec) routing for tool invocations.

ASSUMPTION (recorded 2026-10-02): the "B031 capsec layer" referenced in the
integrations brief is not present on ``origin/main`` of Apeloff1/Skeleton.
The only B031 on main is the *Model capability router* entry in
``skeleton/repo_intelligence/game_creation_batches.json``.  Until that layer
lands, this module defines a minimal pluggable protocol that it can satisfy
by implementing :class:`CapabilityChecker` (``check(request) -> decision``)
and being wired in via :func:`load_checker` / the ``capsec.checker`` config
key.  No adapter code needs to change when it does.

Design rules:

* **Fail closed.**  The default checker denies everything.  Checker
  exceptions, malformed decisions and timeouts are denials.
* **Every invocation is checked**, including tools that declare no
  capabilities: they still need the implicit ``tool.invoke:<name>``.
* **No payload leakage.**  Audit records carry the argument digest, never the
  arguments themselves.
"""

from __future__ import annotations

import fnmatch
import importlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from .errors import CapabilityDeniedError, ConfigurationError

__all__ = [
    "CapabilityRequest",
    "CapabilityDecision",
    "CapabilityChecker",
    "DenyAllChecker",
    "AllowAllChecker",
    "AllowListChecker",
    "CheckerChain",
    "CapsecGate",
    "AuditRecord",
    "implicit_capability",
    "load_checker",
    "B031_INTEGRATION_NOTE",
]

B031_INTEGRATION_NOTE = (
    "B031 capsec layer not found on main; using the pluggable CapabilityChecker protocol with a "
    "fail-closed DenyAllChecker default. Wire the real layer via capsec.checker='module:attr'."
)


def implicit_capability(tool_name: str) -> str:
    return f"tool.invoke:{tool_name}"


@dataclass(frozen=True)
class CapabilityRequest:
    principal: str
    tool: str
    capabilities: tuple[str, ...]
    arguments_digest: str = ""
    resources: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.principal:
            raise ConfigurationError("capability requests need a principal")
        caps = set(self.capabilities)
        caps.add(implicit_capability(self.tool))
        object.__setattr__(self, "capabilities", tuple(sorted(caps)))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    reason: str = ""
    granted: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    checker: str = ""

    @classmethod
    def deny(cls, reason: str, *, denied: Iterable[str] = (), checker: str = "") -> "CapabilityDecision":
        return cls(False, reason, (), tuple(denied), checker)

    @classmethod
    def allow(cls, granted: Iterable[str], *, reason: str = "granted", checker: str = "") -> "CapabilityDecision":
        return cls(True, reason, tuple(granted), (), checker)


@runtime_checkable
class CapabilityChecker(Protocol):
    def check(self, request: CapabilityRequest) -> CapabilityDecision: ...


class DenyAllChecker:
    """The fail-closed default: nothing is permitted until configured."""

    name = "deny_all"

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        return CapabilityDecision.deny(
            "no capability checker configured (fail-closed default)",
            denied=request.capabilities,
            checker=self.name,
        )


class AllowAllChecker:
    """Explicit opt-out for tests and fully trusted local sandboxes only."""

    name = "allow_all"

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        return CapabilityDecision.allow(request.capabilities, reason="allow_all checker", checker=self.name)


class AllowListChecker:
    """Grant capability patterns (fnmatch globs) per principal.

    ``grants={"agent:builder": ["tool.invoke:*", "fs.read"], "*": ["tool.invoke:clock"]}``
    The ``"*"`` principal applies to everyone.  Explicit ``deny`` patterns
    override grants.
    """

    name = "allow_list"

    def __init__(
        self,
        grants: Mapping[str, Iterable[str]],
        *,
        deny: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self._grants = {p: tuple(v) for p, v in grants.items()}
        self._deny = {p: tuple(v) for p, v in (deny or {}).items()}

    def _patterns(self, table: Mapping[str, tuple[str, ...]], principal: str) -> tuple[str, ...]:
        return table.get(principal, ()) + table.get("*", ())

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        grants = self._patterns(self._grants, request.principal)
        denies = self._patterns(self._deny, request.principal)
        blocked = [c for c in request.capabilities if any(fnmatch.fnmatchcase(c, p) for p in denies)]
        if blocked:
            return CapabilityDecision.deny("explicitly denied", denied=blocked, checker=self.name)
        missing = [c for c in request.capabilities if not any(fnmatch.fnmatchcase(c, p) for p in grants)]
        if missing:
            return CapabilityDecision.deny("capability not granted", denied=missing, checker=self.name)
        return CapabilityDecision.allow(request.capabilities, checker=self.name)


class CheckerChain:
    """All checkers must allow; the first denial wins.  Empty chain denies."""

    name = "chain"

    def __init__(self, checkers: Iterable[CapabilityChecker]) -> None:
        self._checkers = tuple(checkers)

    def check(self, request: CapabilityRequest) -> CapabilityDecision:
        if not self._checkers:
            return CapabilityDecision.deny("empty checker chain", denied=request.capabilities, checker=self.name)
        for checker in self._checkers:
            decision = _safe_check(checker, request)
            if not decision.allowed:
                return decision
        return CapabilityDecision.allow(request.capabilities, checker=self.name)


def _checker_name(checker: Any) -> str:
    return str(getattr(checker, "name", type(checker).__name__))


def _safe_check(checker: CapabilityChecker, request: CapabilityRequest) -> CapabilityDecision:
    name = _checker_name(checker)
    try:
        decision = checker.check(request)
    except Exception as exc:  # noqa: BLE001 - a crashing checker is a denial
        return CapabilityDecision.deny(f"checker raised {type(exc).__name__}", denied=request.capabilities,
                                       checker=name)
    if not isinstance(decision, CapabilityDecision):
        return CapabilityDecision.deny("checker returned a malformed decision", denied=request.capabilities,
                                       checker=name)
    if decision.allowed:
        uncovered = set(request.capabilities) - set(decision.granted)
        if uncovered:
            return CapabilityDecision.deny(
                "checker allowed without granting every requested capability",
                denied=sorted(uncovered),
                checker=name,
            )
    return decision


@dataclass(frozen=True)
class AuditRecord:
    at: float
    principal: str
    tool: str
    capabilities: tuple[str, ...]
    allowed: bool
    reason: str
    checker: str
    arguments_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "principal": self.principal,
            "tool": self.tool,
            "capabilities": list(self.capabilities),
            "allowed": self.allowed,
            "reason": self.reason,
            "checker": self.checker,
            "arguments_digest": self.arguments_digest,
        }


class CapsecGate:
    """The single choke point every tool invocation passes through."""

    def __init__(self, checker: CapabilityChecker | None = None, *, audit_limit: int = 1000) -> None:
        self._checker: CapabilityChecker = checker if checker is not None else DenyAllChecker()
        self._audit: deque[AuditRecord] = deque(maxlen=max(1, audit_limit))
        self._lock = threading.Lock()

    @property
    def checker(self) -> CapabilityChecker:
        return self._checker

    @property
    def fail_closed_default(self) -> bool:
        return isinstance(self._checker, DenyAllChecker)

    def decide(self, request: CapabilityRequest) -> CapabilityDecision:
        decision = _safe_check(self._checker, request)
        record = AuditRecord(
            at=time.time(),
            principal=request.principal,
            tool=request.tool,
            capabilities=request.capabilities,
            allowed=decision.allowed,
            reason=decision.reason,
            checker=decision.checker or _checker_name(self._checker),
            arguments_digest=request.arguments_digest,
        )
        with self._lock:
            self._audit.append(record)
        return decision

    def enforce(self, request: CapabilityRequest) -> CapabilityDecision:
        decision = self.decide(request)
        if not decision.allowed:
            denied = ", ".join(decision.denied) or "unspecified"
            raise CapabilityDeniedError(
                f"tool {request.tool!r} denied for {request.principal!r}: {decision.reason} [{denied}]",
                capability=decision.denied[0] if decision.denied else None,
                reason=decision.reason,
                details={"checker": decision.checker, "denied": list(decision.denied)},
            )
        return decision

    def audit(self, limit: int | None = None) -> list[AuditRecord]:
        with self._lock:
            records = list(self._audit)
        return records[-limit:] if limit else records


def load_checker(spec: str, **kwargs: Any) -> CapabilityChecker:
    """Import ``"package.module:attr"`` and return a checker instance.

    ``attr`` may be a class/factory (called with ``kwargs``) or an instance.
    The result must satisfy :class:`CapabilityChecker`; otherwise a
    :class:`ConfigurationError` is raised and nothing is silently allowed.
    Built-in names ``deny_all`` / ``allow_all`` are accepted for config.
    """

    builtins: dict[str, Any] = {"deny_all": DenyAllChecker, "allow_all": AllowAllChecker}
    if spec in builtins:
        return builtins[spec]()
    module_name, sep, attr = spec.partition(":")
    if not sep or not module_name or not attr:
        raise ConfigurationError(f"checker spec {spec!r} must look like 'package.module:attr'")
    try:
        module = importlib.import_module(module_name)
        target = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise ConfigurationError(f"cannot load capability checker {spec!r}: {exc}") from exc
    is_factory = isinstance(target, type) or (callable(target) and not hasattr(target, "check"))
    try:
        instance = target(**kwargs) if is_factory else target
    except Exception as exc:  # noqa: BLE001 - surface as configuration failure
        raise ConfigurationError(f"capability checker factory {spec!r} failed: {exc}") from exc
    if not isinstance(instance, CapabilityChecker):
        raise ConfigurationError(f"{spec!r} does not implement CapabilityChecker.check()")
    return instance
