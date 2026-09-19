"""Append-only durable per-chain index for compaction workflows.

The compaction workflow records themselves are keyed by workflow id, so a
VersionedStateBackend cannot enumerate them without an explicit index.  A
maintenance caller that supplies workflow ids manually can accidentally omit a
PLANNED/CERTIFIED/AUTHORIZED workflow that has not produced a hot floor yet.

This index is metadata only.  It grants no execution or pruning authority.
Index reservation happens before workflow creation so a crash can produce a
visible "indexed but missing workflow" state rather than an undiscoverable
workflow record.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_HASH = "0" * 64


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _digest(
    name: str,
    value: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
    ):
        raise ValueError(
            f"{name} must be 64-character digest"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be hexadecimal"
        ) from exc
    return value.lower()


@dataclass(frozen=True)
class CompactionWorkflowIndexNode:
    chain_id: str
    ordinal: int
    workflow_id: str
    previous_hash: str
    node_hash: str
    indexed_at: float

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal <= 0
        ):
            raise ValueError(
                "workflow index ordinal must be positive"
            )
        object.__setattr__(
            self,
            "workflow_id",
            _digest(
                "workflow_id",
                self.workflow_id,
            ),
        )
        object.__setattr__(
            self,
            "previous_hash",
            _digest(
                "previous_hash",
                self.previous_hash,
            ),
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest(
                "node_hash",
                self.node_hash,
            ),
        )
        if (
            isinstance(self.indexed_at, bool)
            or not isinstance(
                self.indexed_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.indexed_at)
            )
            or float(self.indexed_at) < 0.0
        ):
            raise ValueError(
                "indexed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "indexed_at",
            float(self.indexed_at),
        )
        expected = self.compute_hash(
            self.chain_id,
            self.ordinal,
            self.workflow_id,
            self.previous_hash,
            self.indexed_at,
        )
        if expected != self.node_hash:
            raise ValueError(
                "workflow index node hash mismatch"
            )

    @staticmethod
    def compute_hash(
        chain_id: str,
        ordinal: int,
        workflow_id: str,
        previous_hash: str,
        indexed_at: float,
    ) -> str:
        payload = {
            "chain_id": chain_id,
            "ordinal": ordinal,
            "workflow_id": workflow_id,
            "previous_hash": previous_hash,
            "indexed_at": float(indexed_at),
            "kind": "durable-compaction-workflow-index",
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "ordinal": self.ordinal,
            "workflow_id": self.workflow_id,
            "previous_hash": self.previous_hash,
            "node_hash": self.node_hash,
            "indexed_at": self.indexed_at,
        }


@dataclass(frozen=True)
class CompactionWorkflowIndexHead:
    chain_id: str
    count: int
    node_hash: str

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or self.count < 0
        ):
            raise ValueError(
                "workflow index count must be non-negative"
            )
        object.__setattr__(
            self,
            "node_hash",
            _digest(
                "node_hash",
                self.node_hash,
            ),
        )
        if (
            self.count == 0
            and self.node_hash != GENESIS_HASH
        ):
            raise ValueError(
                "empty workflow index must use genesis hash"
            )
        if (
            self.count > 0
            and self.node_hash == GENESIS_HASH
        ):
            raise ValueError(
                "non-empty workflow index may not use genesis hash"
            )

    @classmethod
    def genesis(
        cls,
        chain_id: str,
    ) -> "CompactionWorkflowIndexHead":
        return cls(
            chain_id,
            0,
            GENESIS_HASH,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "count": self.count,
            "node_hash": self.node_hash,
        }


@dataclass(frozen=True)
class CompactionWorkflowIndexReverse:
    chain_id: str
    workflow_id: str
    ordinal: int
    node_hash: str

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        object.__setattr__(
            self,
            "workflow_id",
            _digest(
                "workflow_id",
                self.workflow_id,
            ),
        )
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal <= 0
        ):
            raise ValueError(
                "workflow reverse ordinal must be positive"
            )
        object.__setattr__(
            self,
            "node_hash",
            _digest(
                "node_hash",
                self.node_hash,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "workflow_id": self.workflow_id,
            "ordinal": self.ordinal,
            "node_hash": self.node_hash,
        }


@dataclass(frozen=True)
class CompactionWorkflowIndexReport:
    chain_id: str
    head: CompactionWorkflowIndexHead
    nodes: tuple[
        CompactionWorkflowIndexNode,
        ...,
    ]
    reverse_indexes_verified: bool
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if self.head.chain_id != self.chain_id:
            raise ValueError(
                "workflow index head chain mismatch"
            )
        nodes = tuple(self.nodes)
        if any(
            item.chain_id != self.chain_id
            for item in nodes
        ):
            raise ValueError(
                "workflow index node chain mismatch"
            )
        object.__setattr__(
            self,
            "nodes",
            nodes,
        )
        if not isinstance(
            self.reverse_indexes_verified,
            bool,
        ):
            raise ValueError(
                "reverse_indexes_verified must be bool"
            )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )

    @property
    def workflow_ids(self) -> tuple[str, ...]:
        return tuple(
            item.workflow_id
            for item in self.nodes
        )

    @property
    def ok(self) -> bool:
        return (
            not self.issues
            and self.reverse_indexes_verified
            and self.head.count == len(self.nodes)
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "ok": self.ok,
            "head": self.head.to_dict(),
            "count": len(self.nodes),
            "workflow_ids": list(
                self.workflow_ids
            ),
            "nodes": [
                item.to_dict()
                for item in self.nodes
            ],
            "reverse_indexes_verified": (
                self.reverse_indexes_verified
            ),
            "issues": list(self.issues),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class CompactionWorkflowIndexError(
    RuntimeError
):
    pass


class DurableCompactionWorkflowIndex:
    """CAS-backed append-only workflow discovery index."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-durable-compaction-workflow-index",
        max_workflows_per_chain: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid workflow index namespace"
            )
        if (
            isinstance(
                max_workflows_per_chain,
                bool,
            )
            or not isinstance(
                max_workflows_per_chain,
                int,
            )
            or max_workflows_per_chain <= 0
        ):
            raise ValueError(
                "max_workflows_per_chain must be positive"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.backend = backend
        self.namespace = namespace
        self.max_workflows_per_chain = (
            max_workflows_per_chain
        )
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def default_namespace(
        operator_namespace: str,
    ) -> str:
        if (
            not isinstance(
                operator_namespace,
                str,
            )
            or not operator_namespace
        ):
            raise ValueError(
                "operator_namespace is required"
            )
        candidate = (
            operator_namespace
            + "-workflow-index"
        )
        if len(candidate) <= 128:
            return candidate
        return (
            "shell-ai-compaction-workflow-index:"
            + hashlib.sha256(
                operator_namespace.encode()
            ).hexdigest()
        )

    @staticmethod
    def _head_key(
        chain_id: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return (
            "head:"
            + hashlib.sha256(
                chain_id.encode()
            ).hexdigest()
        )

    @staticmethod
    def _node_key(
        node_hash: str,
    ) -> str:
        return (
            "node:"
            + _digest(
                "node_hash",
                node_hash,
            )
        )

    @staticmethod
    def _reverse_key(
        workflow_id: str,
    ) -> str:
        return (
            "workflow:"
            + _digest(
                "workflow_id",
                workflow_id,
            )
        )

    @staticmethod
    def _node(
        raw: dict[str, object],
    ) -> CompactionWorkflowIndexNode:
        return CompactionWorkflowIndexNode(
            str(raw["chain_id"]),
            int(raw["ordinal"]),
            str(raw["workflow_id"]),
            str(raw["previous_hash"]),
            str(raw["node_hash"]),
            float(raw["indexed_at"]),
        )

    @staticmethod
    def _head(
        raw: dict[str, object],
    ) -> CompactionWorkflowIndexHead:
        return CompactionWorkflowIndexHead(
            str(raw["chain_id"]),
            int(raw["count"]),
            str(raw["node_hash"]),
        )

    @staticmethod
    def _reverse(
        raw: dict[str, object],
    ) -> CompactionWorkflowIndexReverse:
        return CompactionWorkflowIndexReverse(
            str(raw["chain_id"]),
            str(raw["workflow_id"]),
            int(raw["ordinal"]),
            str(raw["node_hash"]),
        )

    def _head_record(
        self,
        chain_id: str,
    ):
        return self.backend.get(
            self.namespace,
            self._head_key(chain_id),
        )

    def head(
        self,
        chain_id: str,
    ) -> CompactionWorkflowIndexHead:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        record = self._head_record(
            chain_id
        )
        if record is None:
            return (
                CompactionWorkflowIndexHead
                .genesis(chain_id)
            )
        if not isinstance(
            record.value,
            dict,
        ):
            raise CompactionWorkflowIndexError(
                "workflow index head must be mapping"
            )
        head = self._head(
            dict(record.value)
        )
        if head.chain_id != chain_id:
            raise CompactionWorkflowIndexError(
                "workflow index head chain mismatch"
            )
        return head

    def _get_node(
        self,
        node_hash: str,
    ) -> CompactionWorkflowIndexNode:
        record = self.backend.get(
            self.namespace,
            self._node_key(node_hash),
        )
        if record is None:
            raise CompactionWorkflowIndexError(
                "workflow index node is missing"
            )
        if not isinstance(
            record.value,
            dict,
        ):
            raise CompactionWorkflowIndexError(
                "workflow index node must be mapping"
            )
        node = self._node(
            dict(record.value)
        )
        if node.node_hash != node_hash:
            raise CompactionWorkflowIndexError(
                "workflow index node key/hash mismatch"
            )
        return node

    def snapshot(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> tuple[
        CompactionWorkflowIndexNode,
        ...,
    ]:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        if max_items is not None and (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError(
                "max_items must be positive when provided"
            )
        head = self.head(chain_id)
        if head.count == 0:
            return ()
        bound = (
            self.max_workflows_per_chain
            if max_items is None
            else min(
                max_items,
                self.max_workflows_per_chain,
            )
        )
        if head.count > bound:
            raise CompactionWorkflowIndexError(
                "workflow index exceeds traversal bound"
            )

        reverse: list[
            CompactionWorkflowIndexNode
        ] = []
        current_hash = head.node_hash
        expected_ordinal = head.count
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if current_hash in seen:
                raise CompactionWorkflowIndexError(
                    "workflow index contains cycle"
                )
            seen.add(current_hash)
            node = self._get_node(
                current_hash
            )
            if node.chain_id != chain_id:
                raise CompactionWorkflowIndexError(
                    "workflow index node chain mismatch"
                )
            if (
                node.ordinal
                != expected_ordinal
            ):
                raise CompactionWorkflowIndexError(
                    "workflow index ordinal is not contiguous"
                )
            reverse.append(node)
            current_hash = (
                node.previous_hash
            )
            expected_ordinal -= 1
            if len(reverse) > bound:
                raise CompactionWorkflowIndexError(
                    "workflow index traversal bound exceeded"
                )
        if expected_ordinal != 0:
            raise CompactionWorkflowIndexError(
                "workflow index terminated before genesis"
            )
        nodes = tuple(
            reversed(reverse)
        )
        if len(nodes) != head.count:
            raise CompactionWorkflowIndexError(
                "workflow index node count differs from head"
            )
        workflow_ids = tuple(
            item.workflow_id
            for item in nodes
        )
        if len(workflow_ids) != len(
            set(workflow_ids)
        ):
            raise CompactionWorkflowIndexError(
                "workflow index contains duplicate workflow id"
            )
        return nodes

    def _put_node(
        self,
        node: CompactionWorkflowIndexNode,
    ) -> None:
        key = self._node_key(
            node.node_hash
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    node.to_dict(),
                )
                return
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
        if (
            existing is None
            or not isinstance(
                existing.value,
                dict,
            )
        ):
            raise CompactionWorkflowIndexError(
                "workflow index node persistence failed"
            )
        parsed = self._node(
            dict(existing.value)
        )
        if parsed != node:
            raise CompactionWorkflowIndexError(
                "workflow index node hash binds different content"
            )

    def _put_reverse(
        self,
        node: CompactionWorkflowIndexNode,
    ) -> None:
        reverse = CompactionWorkflowIndexReverse(
            node.chain_id,
            node.workflow_id,
            node.ordinal,
            node.node_hash,
        )
        key = self._reverse_key(
            node.workflow_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    reverse.to_dict(),
                )
                return
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
        if (
            existing is None
            or not isinstance(
                existing.value,
                dict,
            )
        ):
            raise CompactionWorkflowIndexError(
                "workflow reverse index persistence failed"
            )
        parsed = self._reverse(
            dict(existing.value)
        )
        if parsed != reverse:
            raise CompactionWorkflowIndexError(
                "workflow id already indexed to different node"
            )

    def _reverse_lookup(
        self,
        workflow_id: str,
    ) -> CompactionWorkflowIndexReverse | None:
        workflow_id = _digest(
            "workflow_id",
            workflow_id,
        )
        record = self.backend.get(
            self.namespace,
            self._reverse_key(
                workflow_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            dict,
        ):
            raise CompactionWorkflowIndexError(
                "workflow reverse index must be mapping"
            )
        reverse = self._reverse(
            dict(record.value)
        )
        if (
            reverse.workflow_id
            != workflow_id
        ):
            raise CompactionWorkflowIndexError(
                "workflow reverse index identity mismatch"
            )
        return reverse

    def _repair_reverse_from_snapshot(
        self,
        chain_id: str,
        workflow_id: str,
    ) -> (
        CompactionWorkflowIndexReverse
        | None
    ):
        for node in self.snapshot(
            chain_id
        ):
            if (
                node.workflow_id
                == workflow_id
            ):
                self._put_reverse(node)
                return CompactionWorkflowIndexReverse(
                    node.chain_id,
                    node.workflow_id,
                    node.ordinal,
                    node.node_hash,
                )
        return None

    def reserve(
        self,
        chain_id: str,
        workflow_id: str,
    ) -> CompactionWorkflowIndexReverse:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        workflow_id = _digest(
            "workflow_id",
            workflow_id,
        )

        existing = self._reverse_lookup(
            workflow_id
        )
        if existing is not None:
            if existing.chain_id != chain_id:
                raise CompactionWorkflowIndexError(
                    "workflow id already indexed under different chain"
                )
            node = self._get_node(
                existing.node_hash
            )
            if (
                node.workflow_id
                != workflow_id
                or node.chain_id
                != chain_id
                or node.ordinal
                != existing.ordinal
            ):
                raise CompactionWorkflowIndexError(
                    "workflow reverse index differs from node"
                )
            return existing

        repaired = (
            self._repair_reverse_from_snapshot(
                chain_id,
                workflow_id,
            )
        )
        if repaired is not None:
            return repaired

        for _ in range(
            self.max_cas_retries
        ):
            record = self._head_record(
                chain_id
            )
            revision = (
                0
                if record is None
                else record.revision
            )
            head = (
                CompactionWorkflowIndexHead
                .genesis(chain_id)
                if record is None
                else self._head(
                    dict(record.value)
                )
            )
            if head.chain_id != chain_id:
                raise CompactionWorkflowIndexError(
                    "workflow index head chain mismatch"
                )
            if (
                head.count
                >= self.max_workflows_per_chain
            ):
                raise CompactionWorkflowIndexError(
                    "workflow index capacity exhausted"
                )
            now = self._clock()
            if (
                isinstance(now, bool)
                or not isinstance(
                    now,
                    (int, float),
                )
                or not math.isfinite(
                    float(now)
                )
                or float(now) < 0.0
            ):
                raise CompactionWorkflowIndexError(
                    "workflow index clock returned invalid time"
                )
            now = float(now)
            ordinal = head.count + 1
            node_hash = (
                CompactionWorkflowIndexNode
                .compute_hash(
                    chain_id,
                    ordinal,
                    workflow_id,
                    head.node_hash,
                    now,
                )
            )
            node = CompactionWorkflowIndexNode(
                chain_id,
                ordinal,
                workflow_id,
                head.node_hash,
                node_hash,
                now,
            )
            self._put_node(node)
            next_head = (
                CompactionWorkflowIndexHead(
                    chain_id,
                    ordinal,
                    node_hash,
                )
            )
            try:
                if revision == 0:
                    self.backend.put_if_absent(
                        self.namespace,
                        self._head_key(
                            chain_id
                        ),
                        next_head.to_dict(),
                    )
                else:
                    self.backend.compare_and_swap(
                        self.namespace,
                        self._head_key(
                            chain_id
                        ),
                        expected_revision=revision,
                        value=next_head.to_dict(),
                    )
            except DistributedStateConflict:
                existing = (
                    self._reverse_lookup(
                        workflow_id
                    )
                )
                if existing is not None:
                    if (
                        existing.chain_id
                        != chain_id
                    ):
                        raise (
                            CompactionWorkflowIndexError(
                                "workflow indexed under different chain"
                            )
                        )
                    return existing
                repaired = (
                    self._repair_reverse_from_snapshot(
                        chain_id,
                        workflow_id,
                    )
                )
                if repaired is not None:
                    return repaired
                continue

            self._put_reverse(node)
            return CompactionWorkflowIndexReverse(
                chain_id,
                workflow_id,
                ordinal,
                node_hash,
            )

        raise CompactionWorkflowIndexError(
            "workflow index CAS retry budget exhausted"
        )

    def contains(
        self,
        chain_id: str,
        workflow_id: str,
    ) -> bool:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        workflow_id = _digest(
            "workflow_id",
            workflow_id,
        )
        reverse = self._reverse_lookup(
            workflow_id
        )
        if reverse is None:
            reverse = (
                self._repair_reverse_from_snapshot(
                    chain_id,
                    workflow_id,
                )
            )
        return bool(
            reverse is not None
            and reverse.chain_id == chain_id
        )

    def workflow_ids(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> tuple[str, ...]:
        return tuple(
            item.workflow_id
            for item in self.snapshot(
                chain_id,
                max_items=max_items,
            )
        )

    def inspect(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> CompactionWorkflowIndexReport:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        issues: list[str] = []
        try:
            head = self.head(
                chain_id
            )
            nodes = self.snapshot(
                chain_id,
                max_items=max_items,
            )
        except Exception as exc:
            head = (
                CompactionWorkflowIndexHead
                .genesis(chain_id)
            )
            nodes = ()
            issues.append(
                "workflow index traversal raised "
                f"{type(exc).__name__}"
            )
            return CompactionWorkflowIndexReport(
                chain_id,
                head,
                nodes,
                False,
                tuple(issues),
            )

        reverse_ok = True
        for node in nodes:
            try:
                reverse = (
                    self._reverse_lookup(
                        node.workflow_id
                    )
                )
                if reverse is None:
                    self._put_reverse(
                        node
                    )
                    reverse = (
                        self._reverse_lookup(
                            node.workflow_id
                        )
                    )
                if (
                    reverse is None
                    or reverse.chain_id
                    != node.chain_id
                    or reverse.ordinal
                    != node.ordinal
                    or reverse.node_hash
                    != node.node_hash
                ):
                    reverse_ok = False
                    issues.append(
                        "workflow reverse index differs from canonical node"
                    )
            except Exception as exc:
                reverse_ok = False
                issues.append(
                    "workflow reverse index verification raised "
                    f"{type(exc).__name__}"
                )

        return CompactionWorkflowIndexReport(
            chain_id,
            head,
            nodes,
            reverse_ok,
            tuple(issues),
        )

    def require(
        self,
        chain_id: str,
        *,
        max_items: int | None = None,
    ) -> CompactionWorkflowIndexReport:
        report = self.inspect(
            chain_id,
            max_items=max_items,
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "workflow index is invalid"
            )
            raise CompactionWorkflowIndexError(
                detail
            )
        return report

    def reserve_many(
        self,
        chain_id: str,
        workflow_ids: Iterable[str],
    ) -> tuple[
        CompactionWorkflowIndexReverse,
        ...,
    ]:
        values = tuple(
            workflow_ids
        )
        if len(values) != len(
            set(values)
        ):
            raise ValueError(
                "duplicate workflow_id"
            )
        return tuple(
            self.reserve(
                chain_id,
                workflow_id,
            )
            for workflow_id in values
        )
