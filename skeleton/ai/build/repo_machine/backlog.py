"""Evidence-derived backlog control for VOL-093.

Backlog definitions, dependencies and provenance are immutable inputs. Lifecycle
state is derived from those inputs plus exact closure evidence; callers cannot
set READY/BLOCKED/CLOSED/RETIRED directly.

Deduplication preserves source provenance and records an alias instead of
rewriting dependency identities. Dependency evaluation resolves aliases, so
work that depended on a duplicate follows the canonical item automatically.
Closure evidence binds the current dependency basis. If upstream state,
dependency topology, item provenance or deduplication changes later, the basis
changes and stale closure evidence no longer yields CLOSED.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

BACKLOG_SCHEMA = "skeleton.repo_machine.backlog.v1"
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ITEMS = 16384
_MAX_DEPENDENCIES = 65536
_MAX_SOURCES_PER_ITEM = 512
_MAX_CLOSURE_AGE_SECONDS = 31_536_000


class BacklogError(ValueError):
    """Backlog definition, topology, disposition or evidence is unsafe."""


class BacklogState(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    CLOSED = "closed"
    RETIRED = "retired"


class SourceKind(str, Enum):
    ISSUE = "issue"
    GAP = "gap"
    RISK = "risk"
    PLAN = "plan"


class DispositionKind(str, Enum):
    DUPLICATE = "duplicate"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise BacklogError(f"{field} must be a stable identifier")
    return value


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 and char not in "\t\n\r" for char in value)
    ):
        raise BacklogError(f"{field} must be normalized bounded text")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise BacklogError(f"{field} must be lowercase sha256")
    return value


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise BacklogError(f"{field} must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        raise BacklogError(f"{field} must use whole-second precision")
    return normalized


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BacklogError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise BacklogError(f"{field} must be within [1, {maximum}]")
    return value


def _digest(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BacklogError("backlog identity must be deterministic JSON") from exc
    return sha256(payload).hexdigest()


def _normalize_semantics(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True, slots=True)
class BacklogSource:
    source_id: str
    kind: SourceKind
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _id(self.source_id, "source_id"),
        )
        if not isinstance(self.kind, SourceKind):
            raise BacklogError("kind must be SourceKind")
        object.__setattr__(
            self,
            "rationale",
            _text(self.rationale, "rationale"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "source_id": self.source_id,
                "kind": self.kind.value,
                "rationale": self.rationale,
            }
        )


@dataclass(frozen=True, slots=True)
class BacklogItem:
    item_id: str
    title: str
    owner: str
    closure_rule: str
    sources: tuple[BacklogSource, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _id(self.item_id, "item_id"))
        object.__setattr__(self, "title", _text(self.title, "title"))
        object.__setattr__(self, "owner", _id(self.owner, "owner"))
        object.__setattr__(
            self,
            "closure_rule",
            _text(self.closure_rule, "closure_rule"),
        )
        if not isinstance(self.sources, tuple):
            raise BacklogError("sources must be a tuple")
        if (
            not self.sources
            or len(self.sources) > _MAX_SOURCES_PER_ITEM
            or any(not isinstance(item, BacklogSource) for item in self.sources)
        ):
            raise BacklogError(
                "backlog item requires bounded typed source provenance"
            )
        ordered = tuple(
            sorted(
                self.sources,
                key=lambda item: (item.kind.value, item.source_id),
            )
        )
        identities = [(item.kind, item.source_id) for item in ordered]
        if len(identities) != len(set(identities)):
            raise BacklogError("duplicate source provenance")
        object.__setattr__(self, "sources", ordered)

    @property
    def fingerprint(self) -> str:
        """Semantic duplicate identity; provenance/owner remain independently preserved."""

        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "title": _normalize_semantics(self.title),
                "closure_rule": _normalize_semantics(self.closure_rule),
            }
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "item_id": self.item_id,
                "title": self.title,
                "owner": self.owner,
                "closure_rule": self.closure_rule,
                "sources": [item.digest for item in self.sources],
            }
        )


@dataclass(frozen=True, slots=True)
class BacklogDependency:
    dependency_id: str
    item_id: str
    depends_on: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dependency_id",
            _id(self.dependency_id, "dependency_id"),
        )
        object.__setattr__(self, "item_id", _id(self.item_id, "item_id"))
        object.__setattr__(
            self,
            "depends_on",
            _id(self.depends_on, "depends_on"),
        )
        object.__setattr__(
            self,
            "rationale",
            _text(self.rationale, "rationale"),
        )
        if self.item_id == self.depends_on:
            raise BacklogError("item cannot depend on itself")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "dependency_id": self.dependency_id,
                "item_id": self.item_id,
                "depends_on": self.depends_on,
                "required_state": BacklogState.CLOSED.value,
                "rationale": self.rationale,
            }
        )


@dataclass(frozen=True, slots=True)
class BacklogDisposition:
    disposition_id: str
    kind: DispositionKind
    item_id: str
    item_digest: str
    target_item_id: str
    target_item_digest_before: str
    target_item_digest_after: str
    actor_id: str
    observed_at: datetime
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "disposition_id",
            _id(self.disposition_id, "disposition_id"),
        )
        if not isinstance(self.kind, DispositionKind):
            raise BacklogError("kind must be DispositionKind")
        for field in ("item_id", "target_item_id", "actor_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        if self.item_id == self.target_item_id:
            raise BacklogError("disposition cannot target itself")
        for field in (
            "item_digest",
            "target_item_digest_before",
            "target_item_digest_after",
        ):
            object.__setattr__(
                self,
                field,
                _sha(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, "reason"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "disposition_id": self.disposition_id,
                "kind": self.kind.value,
                "item_id": self.item_id,
                "item_digest": self.item_digest,
                "target_item_id": self.target_item_id,
                "target_item_digest_before": self.target_item_digest_before,
                "target_item_digest_after": self.target_item_digest_after,
                "actor_id": self.actor_id,
                "observed_at": self.observed_at.isoformat(),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class ClosureEvidence:
    evidence_id: str
    item_id: str
    item_digest: str
    basis_digest: str
    artifact_digest: str
    actor_id: str
    observed_at: datetime
    max_age_seconds: int

    def __post_init__(self) -> None:
        for field in ("evidence_id", "item_id", "actor_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        for field in ("item_digest", "basis_digest", "artifact_digest"):
            object.__setattr__(
                self,
                field,
                _sha(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "max_age_seconds",
            _positive_int(
                self.max_age_seconds,
                "max_age_seconds",
                _MAX_CLOSURE_AGE_SECONDS,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "evidence_id": self.evidence_id,
                "item_id": self.item_id,
                "item_digest": self.item_digest,
                "basis_digest": self.basis_digest,
                "artifact_digest": self.artifact_digest,
                "actor_id": self.actor_id,
                "observed_at": self.observed_at.isoformat(),
                "max_age_seconds": self.max_age_seconds,
            }
        )


@dataclass(frozen=True, slots=True)
class BacklogSnapshot:
    item_id: str
    item_digest: str
    state: BacklogState
    basis_digest: str
    status_digest: str
    dependency_ids: tuple[str, ...]
    closure_evidence_digest: str | None = None
    canonical_item_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _id(self.item_id, "item_id"))
        object.__setattr__(
            self,
            "item_digest",
            _sha(self.item_digest, "item_digest"),
        )
        if not isinstance(self.state, BacklogState):
            raise BacklogError("state must be BacklogState")
        object.__setattr__(
            self,
            "basis_digest",
            _sha(self.basis_digest, "basis_digest"),
        )
        object.__setattr__(
            self,
            "status_digest",
            _sha(self.status_digest, "status_digest"),
        )
        if not isinstance(self.dependency_ids, tuple):
            raise BacklogError("dependency_ids must be a tuple")
        dependency_ids = tuple(
            sorted(_id(item, "dependency_id") for item in self.dependency_ids)
        )
        if len(dependency_ids) != len(set(dependency_ids)):
            raise BacklogError("duplicate dependency identity in snapshot")
        object.__setattr__(self, "dependency_ids", dependency_ids)
        if self.closure_evidence_digest is not None:
            object.__setattr__(
                self,
                "closure_evidence_digest",
                _sha(
                    self.closure_evidence_digest,
                    "closure_evidence_digest",
                ),
            )
        if self.canonical_item_id is not None:
            object.__setattr__(
                self,
                "canonical_item_id",
                _id(self.canonical_item_id, "canonical_item_id"),
            )


class BacklogRegistry:
    """Immutable-definition backlog registry with evidence-derived lifecycle."""

    def __init__(self) -> None:
        self._items: dict[str, BacklogItem] = {}
        self._dependencies: dict[str, BacklogDependency] = {}
        self._aliases: dict[str, str] = {}
        self._dispositions: dict[str, BacklogDisposition] = {}
        self._closure_history: dict[str, ClosureEvidence] = {}
        self._active_closure: dict[str, str] = {}

    def add(self, item: BacklogItem) -> BacklogItem:
        if not isinstance(item, BacklogItem):
            raise TypeError("item must be BacklogItem")
        prior = self._items.get(item.item_id)
        if prior is not None:
            if prior == item:
                return prior
            raise BacklogError("backlog identity is immutable")
        if len(self._items) >= _MAX_ITEMS:
            raise BacklogError("backlog item capacity reached")
        self._items[item.item_id] = item
        return item

    def add_dependency(
        self,
        dependency: BacklogDependency,
    ) -> BacklogDependency:
        if not isinstance(dependency, BacklogDependency):
            raise TypeError("dependency must be BacklogDependency")
        if (
            dependency.item_id not in self._items
            or dependency.depends_on not in self._items
        ):
            raise BacklogError("dependency references unknown item")
        prior = self._dependencies.get(dependency.dependency_id)
        if prior is not None:
            if prior == dependency:
                return prior
            raise BacklogError("dependency identity is immutable")
        if len(self._dependencies) >= _MAX_DEPENDENCIES:
            raise BacklogError("dependency capacity reached")
        if any(
            existing.item_id == dependency.item_id
            and existing.depends_on == dependency.depends_on
            for existing in self._dependencies.values()
        ):
            raise BacklogError("duplicate dependency edge")
        self._dependencies[dependency.dependency_id] = dependency
        try:
            self._assert_acyclic()
        except Exception:
            del self._dependencies[dependency.dependency_id]
            raise
        return dependency

    def _resolve_alias(self, item_id: str) -> str:
        current = _id(item_id, "item_id")
        seen: set[str] = set()
        while current in self._aliases:
            if current in seen:
                raise BacklogError("deduplication alias cycle")
            seen.add(current)
            current = self._aliases[current]
        return current

    def _canonical_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self._resolve_alias(item_id)
                    for item_id in self._items
                }
            )
        )

    def _dependencies_for(
        self,
        canonical_id: str,
    ) -> tuple[BacklogDependency, ...]:
        return tuple(
            sorted(
                (
                    dependency
                    for dependency in self._dependencies.values()
                    if self._resolve_alias(dependency.item_id) == canonical_id
                ),
                key=lambda item: item.dependency_id,
            )
        )

    def _assert_acyclic(self) -> None:
        graph = {
            item_id: set()
            for item_id in self._canonical_ids()
        }
        for dependency in self._dependencies.values():
            source = self._resolve_alias(dependency.item_id)
            target = self._resolve_alias(dependency.depends_on)
            if source == target:
                raise BacklogError(
                    "dependency becomes self-referential after deduplication"
                )
            graph.setdefault(source, set()).add(target)
            graph.setdefault(target, set())

        visiting: set[str] = set()
        done: set[str] = set()

        def visit(item_id: str) -> None:
            if item_id in visiting:
                raise BacklogError("dependency cycle")
            if item_id in done:
                return
            visiting.add(item_id)
            for target in sorted(graph[item_id]):
                visit(target)
            visiting.remove(item_id)
            done.add(item_id)

        for item_id in sorted(graph):
            visit(item_id)

    def duplicates(self, item_id: str) -> tuple[str, ...]:
        canonical = self._resolve_alias(item_id)
        if canonical != item_id:
            raise BacklogError("retired duplicate cannot be duplicate source")
        item = self._items.get(canonical)
        if item is None:
            raise BacklogError("unknown backlog item")
        return tuple(
            sorted(
                candidate_id
                for candidate_id in self._canonical_ids()
                if candidate_id != canonical
                and self._items[candidate_id].fingerprint == item.fingerprint
            )
        )

    def deduplicate(
        self,
        canonical_id: str,
        duplicate_id: str,
        *,
        disposition_id: str,
        actor_id: str,
        observed_at: datetime,
        reason: str,
    ) -> BacklogDisposition:
        canonical_id = _id(canonical_id, "canonical_id")
        duplicate_id = _id(duplicate_id, "duplicate_id")
        if canonical_id == duplicate_id:
            raise BacklogError("item cannot duplicate itself")
        if canonical_id not in self._items or duplicate_id not in self._items:
            raise BacklogError("deduplication references unknown item")
        if (
            self._resolve_alias(canonical_id) != canonical_id
            or self._resolve_alias(duplicate_id) != duplicate_id
        ):
            raise BacklogError("retired duplicate cannot participate in deduplication")

        canonical = self._items[canonical_id]
        duplicate = self._items[duplicate_id]
        if canonical.fingerprint != duplicate.fingerprint:
            raise BacklogError("items are not deterministic duplicates")

        disposition_key = _id(disposition_id, "disposition_id")
        if disposition_key in self._dispositions:
            raise BacklogError("disposition identity is immutable")

        merged_sources = {
            (source.kind, source.source_id): source
            for source in canonical.sources
        }
        for source in duplicate.sources:
            merged_sources[(source.kind, source.source_id)] = source
        merged = replace(
            canonical,
            sources=tuple(merged_sources.values()),
        )

        self._aliases[duplicate_id] = canonical_id
        try:
            self._assert_acyclic()
        except Exception:
            del self._aliases[duplicate_id]
            raise

        disposition = BacklogDisposition(
            disposition_id=disposition_key,
            kind=DispositionKind.DUPLICATE,
            item_id=duplicate_id,
            item_digest=duplicate.digest,
            target_item_id=canonical_id,
            target_item_digest_before=canonical.digest,
            target_item_digest_after=merged.digest,
            actor_id=actor_id,
            observed_at=observed_at,
            reason=reason,
        )
        self._items[canonical_id] = merged
        self._dispositions[disposition.disposition_id] = disposition
        return disposition

    def _retired_snapshot(self, item_id: str) -> BacklogSnapshot:
        canonical = self._resolve_alias(item_id)
        item = self._items[item_id]
        dispositions = tuple(
            sorted(
                (
                    disposition
                    for disposition in self._dispositions.values()
                    if disposition.item_id == item_id
                ),
                key=lambda item: item.disposition_id,
            )
        )
        basis = _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "kind": "retired-basis",
                "item_digest": item.digest,
                "canonical_item_id": canonical,
                "dispositions": [
                    disposition.digest for disposition in dispositions
                ],
            }
        )
        status = _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "item_id": item_id,
                "state": BacklogState.RETIRED.value,
                "basis_digest": basis,
                "canonical_item_id": canonical,
            }
        )
        return BacklogSnapshot(
            item_id=item_id,
            item_digest=item.digest,
            state=BacklogState.RETIRED,
            basis_digest=basis,
            status_digest=status,
            dependency_ids=(),
            canonical_item_id=canonical,
        )

    def _derive(
        self,
        item_id: str,
        memo: dict[str, BacklogSnapshot],
        visiting: set[str],
    ) -> BacklogSnapshot:
        canonical = self._resolve_alias(item_id)
        if canonical != item_id:
            return self._retired_snapshot(item_id)
        if canonical in memo:
            return memo[canonical]
        if canonical in visiting:
            raise BacklogError("dependency cycle during state derivation")
        item = self._items.get(canonical)
        if item is None:
            raise BacklogError("unknown backlog item")

        visiting.add(canonical)
        dependencies = self._dependencies_for(canonical)
        dependency_basis: list[dict[str, str]] = []
        all_closed = True
        for dependency in dependencies:
            target = self._resolve_alias(dependency.depends_on)
            target_snapshot = self._derive(target, memo, visiting)
            dependency_basis.append(
                {
                    "dependency_digest": dependency.digest,
                    "resolved_target": target,
                    "target_state": target_snapshot.state.value,
                    "target_status_digest": target_snapshot.status_digest,
                }
            )
            if target_snapshot.state is not BacklogState.CLOSED:
                all_closed = False

        basis = _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "kind": "closure-basis",
                "item_digest": item.digest,
                "dependencies": dependency_basis,
            }
        )

        closure_digest: str | None = None
        active_id = self._active_closure.get(canonical)
        if active_id is not None:
            closure = self._closure_history[active_id]
            if (
                closure.item_digest == item.digest
                and closure.basis_digest == basis
                and all_closed
            ):
                closure_digest = closure.digest

        if closure_digest is not None:
            state = BacklogState.CLOSED
        else:
            state = (
                BacklogState.READY
                if all_closed
                else BacklogState.BLOCKED
            )

        status = _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "item_id": canonical,
                "item_digest": item.digest,
                "state": state.value,
                "basis_digest": basis,
                "closure_evidence_digest": closure_digest,
            }
        )
        snapshot = BacklogSnapshot(
            item_id=canonical,
            item_digest=item.digest,
            state=state,
            basis_digest=basis,
            status_digest=status,
            dependency_ids=tuple(
                dependency.dependency_id
                for dependency in dependencies
            ),
            closure_evidence_digest=closure_digest,
        )
        visiting.remove(canonical)
        memo[canonical] = snapshot
        return snapshot

    def snapshot(self, item_id: str) -> BacklogSnapshot:
        key = _id(item_id, "item_id")
        if key not in self._items:
            raise BacklogError("unknown backlog item")
        return self._derive(key, {}, set())

    def reconcile_all(self) -> tuple[BacklogSnapshot, ...]:
        memo: dict[str, BacklogSnapshot] = {}
        result: list[BacklogSnapshot] = []
        for item_id in sorted(self._items):
            if item_id in self._aliases:
                result.append(self._retired_snapshot(item_id))
            else:
                result.append(self._derive(item_id, memo, set()))
        return tuple(result)

    def close(
        self,
        item_id: str,
        evidence: ClosureEvidence,
        *,
        at: datetime,
    ) -> BacklogSnapshot:
        key = _id(item_id, "item_id")
        if key in self._aliases:
            raise BacklogError("retired duplicate cannot close")
        if not isinstance(evidence, ClosureEvidence):
            raise TypeError("evidence must be ClosureEvidence")
        now = _utc(at, "closure time")
        snapshot = self.snapshot(key)

        if snapshot.state is BacklogState.CLOSED:
            active_id = self._active_closure[key]
            if self._closure_history[active_id] == evidence:
                return snapshot
            raise BacklogError("backlog item is already closed")
        if snapshot.state is not BacklogState.READY:
            raise BacklogError("blocked item cannot close")

        item = self._items[key]
        if evidence.item_id != key:
            raise BacklogError("closure evidence is bound to another item")
        if evidence.item_digest != item.digest:
            raise BacklogError("closure evidence item digest is stale")
        if evidence.basis_digest != snapshot.basis_digest:
            raise BacklogError("closure evidence dependency basis is stale")
        if evidence.observed_at > now:
            raise BacklogError("closure evidence is future-dated")
        age = (now - evidence.observed_at).total_seconds()
        if age > evidence.max_age_seconds:
            raise BacklogError("closure evidence exceeded freshness policy")

        prior = self._closure_history.get(evidence.evidence_id)
        if prior is not None and prior != evidence:
            raise BacklogError("closure evidence identity is immutable")
        self._closure_history[evidence.evidence_id] = evidence
        self._active_closure[key] = evidence.evidence_id

        closed = self.snapshot(key)
        if closed.state is not BacklogState.CLOSED:
            raise BacklogError("closure evidence did not produce closed state")
        return closed

    def revalidate_dependents(
        self,
        upstream_id: str,
    ) -> tuple[BacklogSnapshot, ...]:
        upstream = self._resolve_alias(upstream_id)
        reverse: dict[str, set[str]] = {}
        for dependency in self._dependencies.values():
            source = self._resolve_alias(dependency.item_id)
            target = self._resolve_alias(dependency.depends_on)
            reverse.setdefault(target, set()).add(source)

        affected: set[str] = set()
        stack = [upstream]
        while stack:
            current = stack.pop()
            for dependent in sorted(reverse.get(current, ())):
                if dependent in affected:
                    continue
                affected.add(dependent)
                stack.append(dependent)
        return tuple(
            self.snapshot(item_id)
            for item_id in sorted(affected)
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": BACKLOG_SCHEMA,
                "items": [
                    self._items[item_id].digest
                    for item_id in sorted(self._items)
                ],
                "dependencies": [
                    self._dependencies[key].digest
                    for key in sorted(self._dependencies)
                ],
                "aliases": [
                    (key, self._aliases[key])
                    for key in sorted(self._aliases)
                ],
                "dispositions": [
                    self._dispositions[key].digest
                    for key in sorted(self._dispositions)
                ],
                "closure_history": [
                    self._closure_history[key].digest
                    for key in sorted(self._closure_history)
                ],
                "active_closure": [
                    (key, self._active_closure[key])
                    for key in sorted(self._active_closure)
                ],
            }
        )


def backlog_rollup(
    registry: BacklogRegistry,
) -> Mapping[str, object]:
    if not isinstance(registry, BacklogRegistry):
        raise TypeError("registry must be BacklogRegistry")
    snapshots = registry.reconcile_all()
    counts = {
        state.value: sum(
            snapshot.state is state
            for snapshot in snapshots
        )
        for state in BacklogState
    }
    return {
        "schema": BACKLOG_SCHEMA,
        "registry_digest": registry.digest,
        "counts": counts,
        "items": [
            {
                "item_id": snapshot.item_id,
                "state": snapshot.state.value,
                "item_digest": snapshot.item_digest,
                "basis_digest": snapshot.basis_digest,
                "status_digest": snapshot.status_digest,
                "closure_evidence_digest": (
                    snapshot.closure_evidence_digest
                ),
                "canonical_item_id": snapshot.canonical_item_id,
            }
            for snapshot in snapshots
        ],
    }


__all__ = [
    "BACKLOG_SCHEMA",
    "BacklogDependency",
    "BacklogDisposition",
    "BacklogError",
    "BacklogItem",
    "BacklogRegistry",
    "BacklogSnapshot",
    "BacklogSource",
    "BacklogState",
    "ClosureEvidence",
    "DispositionKind",
    "SourceKind",
    "backlog_rollup",
]
