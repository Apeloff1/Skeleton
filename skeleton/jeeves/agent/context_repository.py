"""Versioned context repository for long-horizon Jeeves cognition.

This module treats context as owned, auditable state rather than a transcript or
vector-search plugin.  It borrows the useful *shape* of modern context
repositories and agentic context engineering without coupling Jeeves to an
external framework:

* immutable commits over mutable working branches;
* optimistic concurrency and deterministic three-way merge;
* typed context entries with provenance, confidence, salience and retention;
* tombstones instead of destructive deletion;
* protected entries that curation cannot silently rewrite;
* compaction with before/after coverage audits;
* staged offline/sleep-time consolidation rather than live self-mutation;
* bounded retrieval that accounts for relevance, trust, recency and cost.

The language model may propose patches.  Host code validates and commits them.
No model output can directly mutate durable context.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    Claim,
    EvidenceRef,
    MemoryKind,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


class ContextRepositoryError(RuntimeError):
    pass


class ContextConflict(ContextRepositoryError):
    pass


class ContextPolicyViolation(ContextRepositoryError):
    pass


class ContextKind(str, Enum):
    IDENTITY = "identity"
    USER = "user"
    PROJECT = "project"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    STRATEGY = "strategy"
    LESSON = "lesson"
    FAILURE = "failure"
    TOOL = "tool"
    SCRATCH = "scratch"


class PatchOperation(str, Enum):
    UPSERT = "upsert"
    TOMBSTONE = "tombstone"
    RESTORE = "restore"
    PROMOTE = "promote"
    DEMOTE = "demote"
    TOUCH = "touch"


class MergeStrategy(str, Enum):
    FAIL = "fail"
    OURS = "ours"
    THEIRS = "theirs"
    HIGHER_TRUST = "higher_trust"
    NEWER = "newer"


@dataclass(frozen=True, slots=True)
class ContextNamespace:
    tenant_id: str
    user_id: str
    workspace_id: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", require_id("tenant_id", self.tenant_id))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        object.__setattr__(self, "workspace_id", require_id("workspace_id", self.workspace_id))

    @property
    def key(self) -> str:
        return f"{self.tenant_id}/{self.user_id}/{self.workspace_id}"


@dataclass(frozen=True, slots=True)
class ContextEntry:
    entry_id: str
    namespace: ContextNamespace
    key: str
    kind: ContextKind
    content: str
    created_at: float
    updated_at: float
    confidence: float = 0.5
    salience: float = 0.5
    trust: float = 0.5
    source: str = "runtime"
    evidence: tuple[EvidenceRef, ...] = ()
    tags: tuple[str, ...] = ()
    protected: bool = False
    promoted: bool = False
    tombstoned: bool = False
    expires_at: float | None = None
    access_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", require_id("entry_id", self.entry_id))
        if not isinstance(self.namespace, ContextNamespace):
            raise AgentContractError("namespace must be ContextNamespace")
        object.__setattr__(self, "key", require_id("context key", self.key))
        if not isinstance(self.kind, ContextKind):
            object.__setattr__(self, "kind", ContextKind(str(self.kind)))
        object.__setattr__(self, "content", bounded_text("context content", self.content, maximum=96_000, allow_empty=self.tombstoned))
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise AgentContractError("invalid context timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        for name in ("confidence", "salience", "trust"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "source", bounded_text("source", self.source, maximum=1024))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("context evidence must contain EvidenceRef values")
        if len({ref.evidence_id for ref in refs}) != len(refs):
            raise AgentContractError("duplicate context evidence ids")
        object.__setattr__(self, "evidence", refs)
        tags = tuple(sorted({str(tag).strip().casefold() for tag in self.tags if str(tag).strip()}))
        if len(tags) > 128 or any(len(tag) > 128 for tag in tags):
            raise AgentContractError("invalid context tags")
        object.__setattr__(self, "tags", tags)
        if self.expires_at is not None:
            expiry = finite_number("expires_at", self.expires_at)
            if expiry <= created:
                raise AgentContractError("context expiry must be after creation")
            object.__setattr__(self, "expires_at", expiry)
        if isinstance(self.access_count, bool) or not isinstance(self.access_count, int) or self.access_count < 0:
            raise AgentContractError("access_count must be non-negative integer")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def content_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "key": self.key,
                "kind": self.kind.value,
                "content": self.content,
                "source": self.source,
                "evidence": [(ref.evidence_id, ref.fingerprint) for ref in self.evidence],
                "tags": self.tags,
                "protected": self.protected,
                "promoted": self.promoted,
                "tombstoned": self.tombstoned,
            }
        )

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def with_touch(self, now: float) -> "ContextEntry":
        return replace(self, access_count=self.access_count + 1, updated_at=max(self.updated_at, now))


@dataclass(frozen=True, slots=True)
class ContextPatchItem:
    operation: PatchOperation
    key: str
    entry: ContextEntry | None = None
    reason: str = ""
    expected_entry_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, PatchOperation):
            object.__setattr__(self, "operation", PatchOperation(str(self.operation)))
        object.__setattr__(self, "key", require_id("patch key", self.key))
        if self.entry is not None:
            if not isinstance(self.entry, ContextEntry):
                raise AgentContractError("patch entry must be ContextEntry")
            if self.entry.key != self.key:
                raise AgentContractError("patch key/entry key mismatch")
        if self.operation is PatchOperation.UPSERT and self.entry is None:
            raise AgentContractError("upsert requires an entry")
        if self.expected_entry_fingerprint is not None:
            object.__setattr__(self, "expected_entry_fingerprint", str(self.expected_entry_fingerprint).strip().lower())
        object.__setattr__(self, "reason", bounded_text("patch reason", self.reason, maximum=4096, allow_empty=True))


@dataclass(frozen=True, slots=True)
class ContextPatch:
    patch_id: str
    namespace: ContextNamespace
    items: tuple[ContextPatchItem, ...]
    author: str
    created_at: float
    rationale: str = ""
    source_run_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", require_id("patch_id", self.patch_id))
        if not isinstance(self.namespace, ContextNamespace):
            raise AgentContractError("patch namespace must be ContextNamespace")
        items = tuple(self.items)
        if not items or any(not isinstance(item, ContextPatchItem) for item in items):
            raise AgentContractError("patch requires ContextPatchItem values")
        if len(items) > 512:
            raise AgentContractError("patch exceeds item limit")
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "author", require_id("author", self.author))
        created = finite_number("created_at", self.created_at)
        if created < 0:
            raise AgentContractError("patch created_at must be non-negative")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "rationale", bounded_text("rationale", self.rationale, maximum=16_384, allow_empty=True))
        if self.source_run_id is not None:
            object.__setattr__(self, "source_run_id", require_id("source_run_id", self.source_run_id))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace.key,
                "author": self.author,
                "items": [
                    {
                        "op": item.operation.value,
                        "key": item.key,
                        "entry": item.entry.content_fingerprint if item.entry else None,
                        "expected": item.expected_entry_fingerprint,
                        "reason": item.reason,
                    }
                    for item in self.items
                ],
                "rationale": self.rationale,
                "source_run_id": self.source_run_id,
            }
        )


@dataclass(frozen=True, slots=True)
class ContextCommit:
    commit_id: str
    namespace: ContextNamespace
    branch: str
    parent_ids: tuple[str, ...]
    patch_id: str
    patch_fingerprint: str
    snapshot_fingerprint: str
    author: str
    message: str
    created_at: float
    sequence: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_id", require_id("commit_id", self.commit_id))
        if not isinstance(self.namespace, ContextNamespace):
            raise AgentContractError("commit namespace must be ContextNamespace")
        object.__setattr__(self, "branch", require_id("branch", self.branch))
        parents = tuple(require_id("parent_id", parent) for parent in self.parent_ids)
        if len(parents) > 2 or self.commit_id in parents:
            raise AgentContractError("invalid commit parents")
        object.__setattr__(self, "parent_ids", parents)
        object.__setattr__(self, "patch_id", require_id("patch_id", self.patch_id))
        object.__setattr__(self, "author", require_id("author", self.author))
        object.__setattr__(self, "message", bounded_text("commit message", self.message, maximum=4096))
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AgentContractError("commit sequence must be positive")
        object.__setattr__(self, "created_at", finite_number("created_at", self.created_at))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    namespace: ContextNamespace
    branch: str
    head_commit_id: str | None
    entries: tuple[ContextEntry, ...]
    sequence: int
    created_at: float

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace.key,
                "branch": self.branch,
                "head": self.head_commit_id,
                "sequence": self.sequence,
                "entries": [(entry.key, entry.content_fingerprint) for entry in self.entries],
            }
        )

    def by_key(self) -> dict[str, ContextEntry]:
        return {entry.key: entry for entry in self.entries}


@dataclass(frozen=True, slots=True)
class ContextConstitution:
    maximum_entries: int = 10_000
    maximum_active_chars: int = 2_000_000
    maximum_single_entry_chars: int = 96_000
    protected_kinds: tuple[ContextKind, ...] = (ContextKind.IDENTITY, ContextKind.CONSTRAINT)
    require_evidence_for_kinds: tuple[ContextKind, ...] = (ContextKind.SEMANTIC, ContextKind.LESSON)
    minimum_trust_for_promotion: float = 0.75
    minimum_confidence_for_promotion: float = 0.70
    permit_tombstone_protected: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximum_entries", positive_int("maximum_entries", self.maximum_entries, maximum=1_000_000))
        object.__setattr__(self, "maximum_active_chars", positive_int("maximum_active_chars", self.maximum_active_chars, maximum=500_000_000))
        object.__setattr__(self, "maximum_single_entry_chars", positive_int("maximum_single_entry_chars", self.maximum_single_entry_chars, maximum=10_000_000))
        object.__setattr__(self, "protected_kinds", tuple(kind if isinstance(kind, ContextKind) else ContextKind(str(kind)) for kind in self.protected_kinds))
        object.__setattr__(self, "require_evidence_for_kinds", tuple(kind if isinstance(kind, ContextKind) else ContextKind(str(kind)) for kind in self.require_evidence_for_kinds))
        object.__setattr__(self, "minimum_trust_for_promotion", probability("minimum_trust_for_promotion", self.minimum_trust_for_promotion))
        object.__setattr__(self, "minimum_confidence_for_promotion", probability("minimum_confidence_for_promotion", self.minimum_confidence_for_promotion))

    def validate_entry(self, entry: ContextEntry, *, prior: ContextEntry | None = None) -> None:
        if len(entry.content) > self.maximum_single_entry_chars:
            raise ContextPolicyViolation("entry exceeds constitution size limit")
        if entry.kind in self.require_evidence_for_kinds and not entry.evidence and not entry.tombstoned:
            raise ContextPolicyViolation(f"{entry.kind.value} context requires evidence")
        if entry.promoted:
            if entry.trust < self.minimum_trust_for_promotion:
                raise ContextPolicyViolation("promoted context trust below threshold")
            if entry.confidence < self.minimum_confidence_for_promotion:
                raise ContextPolicyViolation("promoted context confidence below threshold")
        if entry.kind in self.protected_kinds and not entry.protected:
            raise ContextPolicyViolation(f"{entry.kind.value} entries must be protected")
        if prior is not None and prior.protected and prior.content_fingerprint != entry.content_fingerprint:
            if not entry.protected:
                raise ContextPolicyViolation("protected entry cannot be silently unprotected")

    def validate_snapshot(self, entries: Sequence[ContextEntry]) -> None:
        if len(entries) > self.maximum_entries:
            raise ContextPolicyViolation("context entry count exceeds constitution")
        active = [entry for entry in entries if not entry.tombstoned]
        if sum(len(entry.content) for entry in active) > self.maximum_active_chars:
            raise ContextPolicyViolation("active context exceeds character budget")
        keys = [entry.key for entry in entries]
        if len(keys) != len(set(keys)):
            raise ContextPolicyViolation("context snapshot contains duplicate keys")


@dataclass(frozen=True, slots=True)
class MergeConflict:
    key: str
    base: ContextEntry | None
    ours: ContextEntry | None
    theirs: ContextEntry | None
    reason: str


@dataclass(frozen=True, slots=True)
class MergeResult:
    merged: bool
    commit: ContextCommit | None
    conflicts: tuple[MergeConflict, ...]
    chosen_keys: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    entry: ContextEntry
    score: float
    lexical: float
    recency: float
    trust: float
    salience: float
    promotion: float
    token_estimate: int


@dataclass(frozen=True, slots=True)
class CompactionAudit:
    before_fingerprint: str
    after_fingerprint: str
    before_active_chars: int
    after_active_chars: int
    protected_preserved: bool
    evidence_coverage_before: int
    evidence_coverage_after: int
    promoted_preserved: bool
    information_retention: float
    accepted: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConsolidationProposal:
    proposal_id: str
    namespace: ContextNamespace
    source_keys: tuple[str, ...]
    target_key: str
    target_kind: ContextKind
    proposed_content: str
    evidence: tuple[EvidenceRef, ...]
    confidence: float
    trust: float
    rationale: str
    fingerprint: str


class ContextRepository:
    """Thread-safe in-memory reference implementation of a context VCS.

    Storage is intentionally abstract at this layer.  A durable implementation
    can persist the same commit/snapshot contracts to SQLite/Postgres/git.
    """

    def __init__(
        self,
        namespace: ContextNamespace,
        *,
        constitution: ContextConstitution | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(namespace, ContextNamespace):
            raise TypeError("namespace must be ContextNamespace")
        self.namespace = namespace
        self.constitution = constitution or ContextConstitution()
        self._clock = clock
        self._commits: dict[str, ContextCommit] = {}
        self._snapshots: dict[str, ContextSnapshot] = {}
        self._patches: dict[str, ContextPatch] = {}
        self._branches: dict[str, str | None] = {"main": None}
        self._sequence = 0
        self._lock = threading.RLock()

    def branches(self) -> Mapping[str, str | None]:
        with self._lock:
            return dict(self._branches)

    def head(self, branch: str = "main") -> str | None:
        branch = require_id("branch", branch)
        with self._lock:
            if branch not in self._branches:
                raise ContextRepositoryError(f"unknown branch: {branch}")
            return self._branches[branch]

    def branch(self, name: str, *, from_branch: str = "main", from_commit: str | None = None) -> str:
        name = require_id("branch", name)
        from_branch = require_id("from_branch", from_branch)
        with self._lock:
            if name in self._branches:
                raise ContextRepositoryError(f"branch already exists: {name}")
            if from_commit is None:
                if from_branch not in self._branches:
                    raise ContextRepositoryError(f"unknown source branch: {from_branch}")
                from_commit = self._branches[from_branch]
            elif from_commit not in self._commits:
                raise ContextRepositoryError(f"unknown source commit: {from_commit}")
            self._branches[name] = from_commit
        return name

    def delete_branch(self, name: str) -> bool:
        name = require_id("branch", name)
        if name == "main":
            raise ContextRepositoryError("main branch cannot be deleted")
        with self._lock:
            return self._branches.pop(name, None) is not None

    def checkout(self, branch: str = "main", *, include_tombstones: bool = True) -> ContextSnapshot:
        branch = require_id("branch", branch)
        with self._lock:
            if branch not in self._branches:
                raise ContextRepositoryError(f"unknown branch: {branch}")
            head = self._branches[branch]
            if head is None:
                snapshot = ContextSnapshot(self.namespace, branch, None, (), 0, self._clock())
            else:
                prior = self._snapshots[head]
                snapshot = ContextSnapshot(self.namespace, branch, head, prior.entries, prior.sequence, self._clock())
        if include_tombstones:
            return snapshot
        return replace(snapshot, entries=tuple(entry for entry in snapshot.entries if not entry.tombstoned))

    def commit(
        self,
        branch: str,
        patch: ContextPatch,
        *,
        message: str,
        expected_head: str | None = None,
        second_parent: str | None = None,
    ) -> ContextCommit:
        branch = require_id("branch", branch)
        if not isinstance(patch, ContextPatch):
            raise TypeError("patch must be ContextPatch")
        if patch.namespace != self.namespace:
            raise ContextRepositoryError("patch namespace mismatch")
        message = bounded_text("commit message", message, maximum=4096)
        with self._lock:
            if branch not in self._branches:
                raise ContextRepositoryError(f"unknown branch: {branch}")
            current_head = self._branches[branch]
            if expected_head != current_head:
                raise ContextConflict(f"head changed: expected {expected_head!r}, current {current_head!r}")
            if second_parent is not None and second_parent not in self._commits:
                raise ContextRepositoryError("second parent does not exist")
            base = self.checkout(branch)
            entries = base.by_key()
            self._apply_patch(entries, patch)
            ordered = tuple(sorted(entries.values(), key=lambda entry: entry.key))
            self.constitution.validate_snapshot(ordered)
            self._sequence += 1
            parents = tuple(parent for parent in (current_head, second_parent) if parent is not None)
            snapshot_fingerprint = stable_fingerprint([(entry.key, entry.content_fingerprint) for entry in ordered])
            commit_id = stable_id(
                "ctxcommit",
                {
                    "namespace": self.namespace.key,
                    "branch": branch,
                    "parents": parents,
                    "patch": patch.fingerprint,
                    "snapshot": snapshot_fingerprint,
                    "sequence": self._sequence,
                },
            )
            commit = ContextCommit(
                commit_id=commit_id,
                namespace=self.namespace,
                branch=branch,
                parent_ids=parents,
                patch_id=patch.patch_id,
                patch_fingerprint=patch.fingerprint,
                snapshot_fingerprint=snapshot_fingerprint,
                author=patch.author,
                message=message,
                created_at=self._clock(),
                sequence=self._sequence,
                metadata={"source_run_id": patch.source_run_id, **dict(patch.metadata)},
            )
            snapshot = ContextSnapshot(
                namespace=self.namespace,
                branch=branch,
                head_commit_id=commit_id,
                entries=ordered,
                sequence=self._sequence,
                created_at=commit.created_at,
            )
            self._patches[patch.patch_id] = patch
            self._commits[commit_id] = commit
            self._snapshots[commit_id] = snapshot
            self._branches[branch] = commit_id
            return commit

    def _apply_patch(self, entries: dict[str, ContextEntry], patch: ContextPatch) -> None:
        now = self._clock()
        for item in patch.items:
            prior = entries.get(item.key)
            if item.expected_entry_fingerprint is not None:
                actual = prior.content_fingerprint if prior else None
                if actual != item.expected_entry_fingerprint:
                    raise ContextConflict(f"entry changed before patch: {item.key}")
            if item.operation is PatchOperation.UPSERT:
                assert item.entry is not None
                entry = item.entry
                if entry.namespace != self.namespace:
                    raise ContextRepositoryError("entry namespace mismatch")
                self.constitution.validate_entry(entry, prior=prior)
                entries[item.key] = entry
            elif item.operation is PatchOperation.TOMBSTONE:
                if prior is None:
                    raise ContextRepositoryError(f"cannot tombstone unknown entry: {item.key}")
                if prior.protected and not self.constitution.permit_tombstone_protected:
                    raise ContextPolicyViolation(f"protected entry cannot be tombstoned: {item.key}")
                entries[item.key] = replace(prior, tombstoned=True, updated_at=now)
            elif item.operation is PatchOperation.RESTORE:
                if prior is None or not prior.tombstoned:
                    raise ContextRepositoryError(f"entry is not tombstoned: {item.key}")
                entries[item.key] = replace(prior, tombstoned=False, updated_at=now)
            elif item.operation is PatchOperation.PROMOTE:
                if prior is None:
                    raise ContextRepositoryError(f"cannot promote unknown entry: {item.key}")
                candidate = replace(prior, promoted=True, updated_at=now)
                self.constitution.validate_entry(candidate, prior=prior)
                entries[item.key] = candidate
            elif item.operation is PatchOperation.DEMOTE:
                if prior is None:
                    raise ContextRepositoryError(f"cannot demote unknown entry: {item.key}")
                if prior.protected:
                    raise ContextPolicyViolation("protected context cannot be demoted")
                entries[item.key] = replace(prior, promoted=False, updated_at=now)
            elif item.operation is PatchOperation.TOUCH:
                if prior is None:
                    raise ContextRepositoryError(f"cannot touch unknown entry: {item.key}")
                entries[item.key] = prior.with_touch(now)

    def commit_by_id(self, commit_id: str) -> ContextCommit:
        with self._lock:
            try:
                return self._commits[require_id("commit_id", commit_id)]
            except KeyError as exc:
                raise ContextRepositoryError(f"unknown commit: {commit_id}") from exc

    def snapshot_at(self, commit_id: str) -> ContextSnapshot:
        with self._lock:
            try:
                return self._snapshots[require_id("commit_id", commit_id)]
            except KeyError as exc:
                raise ContextRepositoryError(f"unknown snapshot commit: {commit_id}") from exc

    def history(self, branch: str = "main", *, limit: int = 100) -> tuple[ContextCommit, ...]:
        branch = require_id("branch", branch)
        limit = positive_int("limit", limit, maximum=100_000)
        head = self.head(branch)
        if head is None:
            return ()
        values: list[ContextCommit] = []
        current = head
        seen: set[str] = set()
        while current and current not in seen and len(values) < limit:
            seen.add(current)
            commit = self.commit_by_id(current)
            values.append(commit)
            current = commit.parent_ids[0] if commit.parent_ids else None
        return tuple(values)

    def ancestor(self, left: str | None, right: str | None) -> str | None:
        if left is None or right is None:
            return None
        left_chain = {commit.commit_id for commit in self._walk_ancestors(left)}
        for commit in self._walk_ancestors(right):
            if commit.commit_id in left_chain:
                return commit.commit_id
        return None

    def _walk_ancestors(self, commit_id: str) -> tuple[ContextCommit, ...]:
        queue = [require_id("commit_id", commit_id)]
        seen: set[str] = set()
        ordered: list[ContextCommit] = []
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            commit = self.commit_by_id(current)
            ordered.append(commit)
            queue.extend(parent for parent in commit.parent_ids if parent not in seen)
        return tuple(ordered)

    def merge(
        self,
        target_branch: str,
        source_branch: str,
        *,
        author: str,
        strategy: MergeStrategy = MergeStrategy.FAIL,
        message: str | None = None,
    ) -> MergeResult:
        target_branch = require_id("target_branch", target_branch)
        source_branch = require_id("source_branch", source_branch)
        author = require_id("author", author)
        if not isinstance(strategy, MergeStrategy):
            strategy = MergeStrategy(str(strategy))
        ours_head = self.head(target_branch)
        theirs_head = self.head(source_branch)
        if theirs_head is None:
            return MergeResult(True, None, (), (), stable_fingerprint((target_branch, source_branch, "noop")))
        if ours_head == theirs_head:
            return MergeResult(True, None, (), (), stable_fingerprint((target_branch, source_branch, "same")))
        base_id = self.ancestor(ours_head, theirs_head)
        base_entries = self.snapshot_at(base_id).by_key() if base_id else {}
        ours_entries = self.checkout(target_branch).by_key()
        theirs_entries = self.checkout(source_branch).by_key()
        merged: dict[str, ContextEntry] = dict(ours_entries)
        conflicts: list[MergeConflict] = []
        chosen: list[str] = []
        for key in sorted(set(base_entries) | set(ours_entries) | set(theirs_entries)):
            base = base_entries.get(key)
            ours = ours_entries.get(key)
            theirs = theirs_entries.get(key)
            base_fp = base.content_fingerprint if base else None
            ours_fp = ours.content_fingerprint if ours else None
            theirs_fp = theirs.content_fingerprint if theirs else None
            if ours_fp == theirs_fp:
                continue
            if ours_fp == base_fp:
                if theirs is None:
                    merged.pop(key, None)
                else:
                    merged[key] = theirs
                chosen.append(key)
                continue
            if theirs_fp == base_fp:
                continue
            conflict = MergeConflict(key, base, ours, theirs, "both branches changed the entry")
            if strategy is MergeStrategy.FAIL:
                conflicts.append(conflict)
                continue
            winner = self._resolve_conflict(conflict, strategy)
            if winner is None:
                merged.pop(key, None)
            else:
                merged[key] = winner
            chosen.append(key)
        if conflicts:
            return MergeResult(False, None, tuple(conflicts), tuple(chosen), stable_fingerprint([(item.key, item.reason) for item in conflicts]))
        patch_items: list[ContextPatchItem] = []
        for key in sorted(set(ours_entries) | set(merged)):
            before = ours_entries.get(key)
            after = merged.get(key)
            if (before.content_fingerprint if before else None) == (after.content_fingerprint if after else None):
                continue
            if after is None:
                if before is not None and not before.tombstoned:
                    patch_items.append(ContextPatchItem(PatchOperation.TOMBSTONE, key, reason=f"merge from {source_branch}"))
            else:
                patch_items.append(ContextPatchItem(PatchOperation.UPSERT, key, entry=after, reason=f"merge from {source_branch}"))
        if not patch_items:
            return MergeResult(True, None, (), tuple(chosen), stable_fingerprint((target_branch, source_branch, "resolved-noop")))
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"target": target_branch, "source": source_branch, "head": theirs_head, "items": [(item.operation.value, item.key) for item in patch_items]}),
            namespace=self.namespace,
            items=tuple(patch_items),
            author=author,
            created_at=self._clock(),
            rationale=f"three-way merge {source_branch} into {target_branch}",
            metadata={"merge_base": base_id, "strategy": strategy.value},
        )
        commit = self.commit(
            target_branch,
            patch,
            message=message or f"merge {source_branch} into {target_branch}",
            expected_head=ours_head,
            second_parent=theirs_head,
        )
        return MergeResult(True, commit, (), tuple(chosen), stable_fingerprint((commit.commit_id, tuple(chosen))))

    @staticmethod
    def _resolve_conflict(conflict: MergeConflict, strategy: MergeStrategy) -> ContextEntry | None:
        if strategy is MergeStrategy.OURS:
            return conflict.ours
        if strategy is MergeStrategy.THEIRS:
            return conflict.theirs
        candidates = [entry for entry in (conflict.ours, conflict.theirs) if entry is not None]
        if not candidates:
            return None
        if strategy is MergeStrategy.HIGHER_TRUST:
            return max(candidates, key=lambda entry: (entry.trust, entry.confidence, entry.updated_at, entry.content_fingerprint))
        if strategy is MergeStrategy.NEWER:
            return max(candidates, key=lambda entry: (entry.updated_at, entry.trust, entry.content_fingerprint))
        raise ContextConflict(conflict.reason)

    def retrieve(
        self,
        query: str,
        *,
        branch: str = "main",
        kinds: Sequence[ContextKind] | None = None,
        tags: Sequence[str] = (),
        max_entries: int = 12,
        max_tokens: int = 4_000,
        minimum_trust: float = 0.0,
        include_unpromoted: bool = True,
        touch: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        max_entries = positive_int("max_entries", max_entries, maximum=10_000)
        max_tokens = positive_int("max_tokens", max_tokens, maximum=1_000_000)
        minimum_trust = probability("minimum_trust", minimum_trust)
        kind_set = None if kinds is None else {kind if isinstance(kind, ContextKind) else ContextKind(str(kind)) for kind in kinds}
        tag_set = {str(tag).strip().casefold() for tag in tags if str(tag).strip()}
        query_tokens = self._tokens(query)
        now = self._clock()
        candidates: list[RetrievalHit] = []
        for entry in self.checkout(branch, include_tombstones=False).entries:
            if entry.expired(now) or entry.trust < minimum_trust:
                continue
            if kind_set is not None and entry.kind not in kind_set:
                continue
            if tag_set and not tag_set.issubset(set(entry.tags)):
                continue
            if not include_unpromoted and not entry.promoted:
                continue
            lexical = self._cosine(query_tokens, self._tokens(entry.content + " " + " ".join(entry.tags)))
            age = max(0.0, now - entry.updated_at)
            recency = math.exp(-math.log(2) * age / (14 * 24 * 3600))
            promotion = 1.0 if entry.promoted else 0.0
            score = lexical * 0.48 + recency * 0.10 + entry.trust * 0.18 + entry.salience * 0.12 + entry.confidence * 0.07 + promotion * 0.05
            tokens = max(1, len(entry.content) // 4)
            candidates.append(RetrievalHit(entry, score, lexical, recency, entry.trust, entry.salience, promotion, tokens))
        candidates.sort(key=lambda hit: (hit.score, hit.entry.promoted, hit.entry.updated_at, hit.entry.key), reverse=True)
        chosen: list[RetrievalHit] = []
        used = 0
        for hit in candidates:
            if len(chosen) >= max_entries:
                break
            if chosen and used + hit.token_estimate > max_tokens:
                continue
            chosen.append(hit)
            used += hit.token_estimate
        if touch and chosen:
            self._touch_hits(branch, chosen)
        return tuple(chosen)

    def _touch_hits(self, branch: str, hits: Sequence[RetrievalHit]) -> None:
        head = self.head(branch)
        snapshot = self.checkout(branch)
        entries = snapshot.by_key()
        items: list[ContextPatchItem] = []
        for hit in hits:
            prior = entries.get(hit.entry.key)
            if prior is not None:
                items.append(ContextPatchItem(PatchOperation.TOUCH, prior.key, expected_entry_fingerprint=prior.content_fingerprint, reason="retrieval access"))
        if not items:
            return
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"touch": [(item.key, item.expected_entry_fingerprint) for item in items], "head": head}),
            namespace=self.namespace,
            items=tuple(items),
            author="retriever",
            created_at=self._clock(),
            rationale="record context retrieval access",
        )
        self.commit(branch, patch, message="touch retrieved context", expected_head=head)

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        return Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(count * right.get(token, 0) for token, count in left.items())
        ln = math.sqrt(sum(value * value for value in left.values()))
        rn = math.sqrt(sum(value * value for value in right.values()))
        return max(0.0, min(1.0, dot / (ln * rn))) if ln and rn else 0.0

    def audit_compaction(self, before: ContextSnapshot, after_entries: Sequence[ContextEntry], *, minimum_retention: float = 0.90) -> CompactionAudit:
        minimum_retention = probability("minimum_retention", minimum_retention)
        after = tuple(sorted(after_entries, key=lambda entry: entry.key))
        self.constitution.validate_snapshot(after)
        before_active = [entry for entry in before.entries if not entry.tombstoned]
        after_active = [entry for entry in after if not entry.tombstoned]
        before_map = {entry.key: entry for entry in before.entries}
        after_map = {entry.key: entry for entry in after}
        protected_preserved = all(
            key in after_map and after_map[key].content_fingerprint == entry.content_fingerprint
            for key, entry in before_map.items()
            if entry.protected and not entry.tombstoned
        )
        promoted_preserved = all(
            key in after_map and not after_map[key].tombstoned
            for key, entry in before_map.items()
            if entry.promoted and not entry.tombstoned
        )
        before_evidence = {ref.evidence_id for entry in before_active for ref in entry.evidence}
        after_evidence = {ref.evidence_id for entry in after_active for ref in entry.evidence}
        evidence_retention = len(before_evidence & after_evidence) / len(before_evidence) if before_evidence else 1.0
        promoted_keys = {entry.key for entry in before_active if entry.promoted}
        semantic_keys = {entry.key for entry in before_active if entry.kind in {ContextKind.SEMANTIC, ContextKind.PROCEDURAL, ContextKind.LESSON, ContextKind.CONSTRAINT}}
        important = promoted_keys | semantic_keys
        important_retention = sum(1 for key in important if key in after_map and not after_map[key].tombstoned) / len(important) if important else 1.0
        information_retention = min(evidence_retention, important_retention)
        reasons: list[str] = []
        if not protected_preserved:
            reasons.append("protected entries changed or disappeared")
        if not promoted_preserved:
            reasons.append("promoted entries disappeared")
        if information_retention < minimum_retention:
            reasons.append(f"information retention {information_retention:.3f} below {minimum_retention:.3f}")
        accepted = protected_preserved and promoted_preserved and information_retention >= minimum_retention
        return CompactionAudit(
            before_fingerprint=before.fingerprint,
            after_fingerprint=stable_fingerprint([(entry.key, entry.content_fingerprint) for entry in after]),
            before_active_chars=sum(len(entry.content) for entry in before_active),
            after_active_chars=sum(len(entry.content) for entry in after_active),
            protected_preserved=protected_preserved,
            evidence_coverage_before=len(before_evidence),
            evidence_coverage_after=len(after_evidence),
            promoted_preserved=promoted_preserved,
            information_retention=information_retention,
            accepted=accepted,
            reasons=tuple(reasons),
        )

    def compact(
        self,
        branch: str,
        replacements: Sequence[ContextEntry],
        tombstone_keys: Sequence[str],
        *,
        author: str,
        minimum_retention: float = 0.90,
        message: str = "validated context compaction",
    ) -> tuple[ContextCommit, CompactionAudit]:
        before = self.checkout(branch)
        after_map = before.by_key()
        for key in tombstone_keys:
            key = require_id("tombstone key", key)
            prior = after_map.get(key)
            if prior is None:
                raise ContextRepositoryError(f"unknown compaction key: {key}")
            if prior.protected and not self.constitution.permit_tombstone_protected:
                raise ContextPolicyViolation(f"protected entry cannot be compacted away: {key}")
            after_map[key] = replace(prior, tombstoned=True, updated_at=self._clock())
        for replacement in replacements:
            if replacement.namespace != self.namespace:
                raise ContextRepositoryError("compaction replacement namespace mismatch")
            self.constitution.validate_entry(replacement, prior=after_map.get(replacement.key))
            after_map[replacement.key] = replacement
        audit = self.audit_compaction(before, tuple(after_map.values()), minimum_retention=minimum_retention)
        if not audit.accepted:
            raise ContextPolicyViolation("compaction audit rejected: " + "; ".join(audit.reasons))
        items: list[ContextPatchItem] = []
        for key in tombstone_keys:
            items.append(ContextPatchItem(PatchOperation.TOMBSTONE, key, reason="validated compaction"))
        for replacement in replacements:
            prior = before.by_key().get(replacement.key)
            items.append(ContextPatchItem(PatchOperation.UPSERT, replacement.key, entry=replacement, expected_entry_fingerprint=prior.content_fingerprint if prior else None, reason="validated compaction replacement"))
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"compaction": audit.after_fingerprint, "before": audit.before_fingerprint}),
            namespace=self.namespace,
            items=tuple(items),
            author=author,
            created_at=self._clock(),
            rationale="context compaction passed retention audit",
            metadata={"compaction_audit": audit.after_fingerprint, "retention": audit.information_retention},
        )
        commit = self.commit(branch, patch, message=message, expected_head=before.head_commit_id)
        return commit, audit

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(
                {
                    "namespace": self.namespace.key,
                    "branches": self._branches,
                    "commits": [(commit_id, commit.snapshot_fingerprint, commit.parent_ids) for commit_id, commit in sorted(self._commits.items())],
                }
            )


class ContextCurator:
    """Construct host-validatable context patches from verified run material."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock

    def from_claims(
        self,
        namespace: ContextNamespace,
        claims: Sequence[Claim],
        *,
        author: str = "curator",
        source_run_id: str | None = None,
    ) -> ContextPatch | None:
        items: list[ContextPatchItem] = []
        now = self._clock()
        for claim in claims:
            if not claim.evidence:
                continue
            key = stable_id("claimctx", {"subject": claim.subject, "text": claim.text}, length=24)
            entry = ContextEntry(
                entry_id=stable_id("ctx", {"key": key, "claim": claim.claim_id}),
                namespace=namespace,
                key=key,
                kind=ContextKind.SEMANTIC,
                content=claim.text,
                created_at=now,
                updated_at=now,
                confidence=claim.confidence,
                salience=min(1.0, 0.45 + 0.4 * claim.confidence),
                trust=min(ref.confidence for ref in claim.evidence),
                source=f"claim:{claim.claim_id}",
                evidence=claim.evidence,
                tags=tuple(tag for tag in ("claim", claim.subject or "") if tag),
                promoted=False,
                metadata={"claim_id": claim.claim_id, "derived": claim.derived},
            )
            items.append(ContextPatchItem(PatchOperation.UPSERT, key, entry=entry, reason="grounded claim candidate"))
        if not items:
            return None
        return ContextPatch(
            patch_id=stable_id("ctxpatch", {"claims": [item.key for item in items], "run": source_run_id}),
            namespace=namespace,
            items=tuple(items),
            author=author,
            created_at=now,
            rationale="stage grounded claims as semantic context",
            source_run_id=source_run_id,
        )

    def from_failure(
        self,
        namespace: ContextNamespace,
        *,
        failure_key: str,
        description: str,
        evidence: Sequence[EvidenceRef] = (),
        trust: float = 0.7,
        source_run_id: str | None = None,
    ) -> ContextPatch:
        now = self._clock()
        key = require_id("failure_key", failure_key)
        refs = tuple(evidence)
        entry = ContextEntry(
            entry_id=stable_id("ctx", {"failure": key, "description": description, "run": source_run_id}),
            namespace=namespace,
            key=key,
            kind=ContextKind.FAILURE,
            content=description,
            created_at=now,
            updated_at=now,
            confidence=0.8,
            salience=0.75,
            trust=trust,
            source="verified-failure",
            evidence=refs,
            tags=("failure", "lesson-candidate"),
            metadata={"source_run_id": source_run_id},
        )
        return ContextPatch(
            patch_id=stable_id("ctxpatch", {"failure": entry.content_fingerprint}),
            namespace=namespace,
            items=(ContextPatchItem(PatchOperation.UPSERT, key, entry=entry, reason="verified failure episode"),),
            author="curator",
            created_at=now,
            rationale="retain verified failure for later consolidation",
            source_run_id=source_run_id,
        )


class SleepTimeConsolidator:
    """Propose offline context consolidation without mutating the repository.

    The caller may run this during idle/sleep-time compute, inspect proposals,
    validate them, and then convert selected proposals into normal patches.
    """

    def __init__(self, *, minimum_group_size: int = 2) -> None:
        self.minimum_group_size = positive_int("minimum_group_size", minimum_group_size, maximum=1000)

    def propose(self, snapshot: ContextSnapshot, *, maximum: int = 32) -> tuple[ConsolidationProposal, ...]:
        maximum = positive_int("maximum", maximum, maximum=1000)
        groups: dict[tuple[ContextKind, str], list[ContextEntry]] = defaultdict(list)
        for entry in snapshot.entries:
            if entry.tombstoned or entry.protected or entry.kind not in {ContextKind.EPISODIC, ContextKind.FAILURE, ContextKind.STRATEGY, ContextKind.LESSON}:
                continue
            topic = self._topic(entry)
            groups[(entry.kind, topic)].append(entry)
        proposals: list[ConsolidationProposal] = []
        for (kind, topic), entries in sorted(groups.items(), key=lambda item: item[0][1]):
            if len(entries) < self.minimum_group_size:
                continue
            entries.sort(key=lambda entry: (entry.trust, entry.confidence, entry.updated_at), reverse=True)
            evidence_by_id: dict[str, EvidenceRef] = {}
            for entry in entries:
                for ref in entry.evidence:
                    evidence_by_id[ref.evidence_id] = ref
            lines = [entry.content for entry in entries[:8]]
            content = "\n".join(f"- {line}" for line in lines)
            target_kind = ContextKind.LESSON if kind in {ContextKind.FAILURE, ContextKind.EPISODIC} else ContextKind.STRATEGY
            target_key = stable_id("consolidated", {"kind": target_kind.value, "topic": topic}, length=24)
            trust = sum(entry.trust for entry in entries) / len(entries)
            confidence = sum(entry.confidence for entry in entries) / len(entries)
            proposal_id = stable_id("ctxproposal", {"sources": [entry.entry_id for entry in entries], "target": target_key})
            proposals.append(
                ConsolidationProposal(
                    proposal_id=proposal_id,
                    namespace=snapshot.namespace,
                    source_keys=tuple(entry.key for entry in entries),
                    target_key=target_key,
                    target_kind=target_kind,
                    proposed_content=content,
                    evidence=tuple(sorted(evidence_by_id.values(), key=lambda ref: ref.evidence_id)),
                    confidence=min(0.98, confidence),
                    trust=min(0.98, trust),
                    rationale=f"consolidate {len(entries)} related {kind.value} records around {topic}",
                    fingerprint=stable_fingerprint((proposal_id, content, sorted(evidence_by_id))),
                )
            )
        proposals.sort(key=lambda proposal: (proposal.trust * proposal.confidence, len(proposal.source_keys), proposal.proposal_id), reverse=True)
        return tuple(proposals[:maximum])

    def patch_from_proposal(self, proposal: ConsolidationProposal, *, author: str = "sleep-curator", tombstone_sources: bool = False, clock: Callable[[], float] = time.time) -> ContextPatch:
        now = clock()
        entry = ContextEntry(
            entry_id=stable_id("ctx", {"proposal": proposal.proposal_id, "fingerprint": proposal.fingerprint}),
            namespace=proposal.namespace,
            key=proposal.target_key,
            kind=proposal.target_kind,
            content=proposal.proposed_content,
            created_at=now,
            updated_at=now,
            confidence=proposal.confidence,
            salience=min(1.0, 0.55 + len(proposal.source_keys) * 0.03),
            trust=proposal.trust,
            source=f"consolidation:{proposal.proposal_id}",
            evidence=proposal.evidence,
            tags=("consolidated", proposal.target_kind.value),
            promoted=False,
            metadata={"source_keys": proposal.source_keys, "proposal_id": proposal.proposal_id},
        )
        items: list[ContextPatchItem] = [ContextPatchItem(PatchOperation.UPSERT, entry.key, entry=entry, reason=proposal.rationale)]
        if tombstone_sources:
            items.extend(ContextPatchItem(PatchOperation.TOMBSTONE, key, reason=f"superseded by {proposal.target_key}") for key in proposal.source_keys)
        return ContextPatch(
            patch_id=stable_id("ctxpatch", {"proposal": proposal.proposal_id, "tombstone": tombstone_sources}),
            namespace=proposal.namespace,
            items=tuple(items),
            author=author,
            created_at=now,
            rationale=proposal.rationale,
            metadata={"proposal_fingerprint": proposal.fingerprint},
        )

    @staticmethod
    def _topic(entry: ContextEntry) -> str:
        tags = [tag for tag in entry.tags if tag not in {"failure", "lesson-candidate", "consolidated"}]
        if tags:
            return tags[0][:64]
        tokens = [token.casefold() for token in _TOKEN_RE.findall(entry.content)]
        common = Counter(tokens).most_common(3)
        return "-".join(token for token, _ in common)[:64] or entry.kind.value


def namespace_from_memory_ids(tenant_id: str, user_id: str, workspace_id: str = "default") -> ContextNamespace:
    return ContextNamespace(tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id)


def context_kind_from_memory(kind: MemoryKind) -> ContextKind:
    mapping = {
        MemoryKind.WORKING: ContextKind.SCRATCH,
        MemoryKind.EPISODIC: ContextKind.EPISODIC,
        MemoryKind.SEMANTIC: ContextKind.SEMANTIC,
        MemoryKind.PROCEDURAL: ContextKind.PROCEDURAL,
        MemoryKind.PREFERENCE: ContextKind.PREFERENCE,
        MemoryKind.PROFILE: ContextKind.USER,
    }
    return mapping[kind]
