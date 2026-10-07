"""Signed checkpoints for long-lived durable evidence chains.

Checkpoints provide an externally signed commitment to a committed historical
root and sequence.  They are useful for archival, audits, and retention
planning.  They do not delete evidence and do not by themselves make pruning
safe; historical readers still require the underlying committed nodes unless an
archive-backed reader is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Protocol, runtime_checkable

from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceCorruption,
    EvidenceStateBackend,
)


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@runtime_checkable
class CheckpointableEvidenceChain(Protocol):
    def head(self): ...

    def verify(self) -> bool: ...

    def verify_root(self, root_hash: str) -> bool: ...

    def root_is_ancestor(self, root_hash: str) -> bool: ...

    def snapshot_at(self, root_hash: str): ...


@dataclass(frozen=True)
class DurableChainCheckpoint:
    schema_version: int
    chain_id: str
    sequence: int
    root_hash: str
    previous_checkpoint_digest: str
    observed_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable chain checkpoint schema"
            )
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid durable chain checkpoint chain_id"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "durable chain checkpoint sequence must be non-negative"
            )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        object.__setattr__(
            self,
            "previous_checkpoint_digest",
            _digest(
                "previous_checkpoint_digest",
                self.previous_checkpoint_digest,
                optional=True,
            ),
        )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or not math.isfinite(float(self.observed_at))
            or float(self.observed_at) < 0.0
        ):
            raise ValueError(
                "durable checkpoint observed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "observed_at",
            float(self.observed_at),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "previous_checkpoint_digest": (
                self.previous_checkpoint_digest
            ),
            "observed_at": self.observed_at,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedDurableChainCheckpoint:
    checkpoint: DurableChainCheckpoint
    signature: SignedArtifact
    chain_node_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_node_hash",
            _digest(
                "chain_node_hash",
                self.chain_node_hash,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint.to_dict(),
            "checkpoint_digest": self.checkpoint.digest,
            "signature": self.signature.to_dict(),
            "chain_node_hash": self.chain_node_hash,
        }


@dataclass(frozen=True)
class DurableCheckpointVerification:
    valid: bool
    chain_id: str
    sequence: int
    root_hash: str
    current_sequence: int
    current_root: str
    root_is_ancestor: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid chain_id")
        for name in (
            "sequence",
            "current_sequence",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative"
                )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        object.__setattr__(
            self,
            "current_root",
            _digest("current_root", self.current_root),
        )
        if not isinstance(
            self.root_is_ancestor,
            bool,
        ):
            raise ValueError(
                "root_is_ancestor must be bool"
            )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "root_is_ancestor": self.root_is_ancestor,
            "reasons": list(self.reasons),
        }


class DurableCheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class DurableCheckpointLookupIndex:
    chain_id: str
    sequence: int
    root_hash: str
    checkpoint_digest: str
    chain_node_hash: str

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid durable checkpoint lookup chain_id"
            )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "durable checkpoint lookup sequence must be non-negative"
            )
        for name in (
            "root_hash",
            "checkpoint_digest",
            "chain_node_hash",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "checkpoint_digest": self.checkpoint_digest,
            "chain_node_hash": self.chain_node_hash,
        }


class DurableCheckpointIndexState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableCheckpointIndexHealth:
    chain_id: str
    state: DurableCheckpointIndexState
    registry_valid: bool
    checkpoint_count: int
    digest_indexes_present: int
    root_indexes_present: int
    missing_digest_indexes: tuple[str, ...]
    missing_root_indexes: tuple[str, ...]
    corrupt_indexes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid checkpoint index health chain_id"
            )
        object.__setattr__(
            self,
            "state",
            DurableCheckpointIndexState(
                self.state
            ),
        )
        if not isinstance(
            self.registry_valid,
            bool,
        ):
            raise ValueError(
                "registry_valid must be bool"
            )
        for name in (
            "checkpoint_count",
            "digest_indexes_present",
            "root_indexes_present",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        for name in (
            "missing_digest_indexes",
            "missing_root_indexes",
            "corrupt_indexes",
        ):
            values = tuple(
                getattr(self, name)
            )
            if any(
                not isinstance(item, str)
                or not item
                or len(item) > 512
                for item in values
            ):
                raise ValueError(
                    f"invalid {name}"
                )
            object.__setattr__(
                self,
                name,
                values,
            )

    @property
    def missing(self) -> int:
        return (
            len(self.missing_digest_indexes)
            + len(self.missing_root_indexes)
        )

    @property
    def corrupt(self) -> int:
        return len(self.corrupt_indexes)

    @property
    def healthy(self) -> bool:
        return (
            self.state
            is DurableCheckpointIndexState.HEALTHY
        )

    @property
    def repairable(self) -> bool:
        return (
            self.registry_valid
            and not self.corrupt_indexes
            and self.missing > 0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "registry_valid": self.registry_valid,
            "checkpoint_count": self.checkpoint_count,
            "digest_indexes_present": (
                self.digest_indexes_present
            ),
            "root_indexes_present": (
                self.root_indexes_present
            ),
            "missing_digest_indexes": list(
                self.missing_digest_indexes
            ),
            "missing_root_indexes": list(
                self.missing_root_indexes
            ),
            "corrupt_indexes": list(
                self.corrupt_indexes
            ),
            "missing": self.missing,
            "corrupt": self.corrupt,
            "healthy": self.healthy,
            "repairable": self.repairable,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class DurableChainCheckpointStore:
    """Append-only signed checkpoint history for one or more evidence chains."""

    def __init__(
        self,
        backend: EvidenceStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-checkpoint",
        max_checkpoints: int = 100_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(signer, ArtifactSigner):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable checkpoint namespace"
            )
        if (
            isinstance(max_checkpoints, bool)
            or not isinstance(max_checkpoints, int)
            or max_checkpoints <= 0
        ):
            raise ValueError(
                "max_checkpoints must be positive integer"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.signer = signer
        self._clock = clock
        self._backend = backend
        self._namespace = namespace
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_checkpoints,
        )

    @staticmethod
    def _root_lookup_key(
        chain_id: str,
        root_hash: str,
    ) -> str:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "root_hash": root_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return (
            "checkpoint-root:"
            + hashlib.sha256(raw).hexdigest()
        )

    @staticmethod
    def _digest_lookup_key(
        checkpoint_digest: str,
    ) -> str:
        checkpoint_digest = _digest(
            "checkpoint_digest",
            checkpoint_digest,
        )
        return (
            "checkpoint-digest:"
            + checkpoint_digest
        )

    @staticmethod
    def _lookup(
        raw: dict[str, object],
    ) -> DurableCheckpointLookupIndex:
        return DurableCheckpointLookupIndex(
            str(raw["chain_id"]),
            int(raw["sequence"]),
            str(raw["root_hash"]),
            str(raw["checkpoint_digest"]),
            str(raw["chain_node_hash"]),
        )

    @staticmethod
    def _lookup_for(
        item: SignedDurableChainCheckpoint,
    ) -> DurableCheckpointLookupIndex:
        return DurableCheckpointLookupIndex(
            item.checkpoint.chain_id,
            item.checkpoint.sequence,
            item.checkpoint.root_hash,
            item.checkpoint.digest,
            item.chain_node_hash,
        )

    def _put_lookup(
        self,
        key: str,
        lookup: DurableCheckpointLookupIndex,
    ) -> bool:
        value = lookup.to_dict()
        existing = self._backend.get(
            self._namespace,
            key,
        )
        if existing is None:
            try:
                self._backend.put_if_absent(
                    self._namespace,
                    key,
                    value,
                )
                return True
            except Exception:
                existing = self._backend.get(
                    self._namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(existing.value, dict):
            raise DurableCheckpointError(
                "durable checkpoint lookup index must be mapping"
            )
        current = self._lookup(
            dict(existing.value)
        )
        if current != lookup:
            raise DurableCheckpointError(
                "durable checkpoint lookup key binds different checkpoint"
            )
        return False

    def _index_item(
        self,
        item: SignedDurableChainCheckpoint,
    ) -> int:
        lookup = self._lookup_for(item)
        written = 0
        if self._put_lookup(
            self._digest_lookup_key(
                lookup.checkpoint_digest
            ),
            lookup,
        ):
            written += 1
        if self._put_lookup(
            self._root_lookup_key(
                lookup.chain_id,
                lookup.root_hash,
            ),
            lookup,
        ):
            written += 1
        return written

    def _lookup_record(
        self,
        key: str,
    ) -> DurableCheckpointLookupIndex | None:
        record = self._backend.get(
            self._namespace,
            key,
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableCheckpointError(
                "durable checkpoint lookup index must be mapping"
            )
        return self._lookup(
            dict(record.value)
        )

    def _item_from_lookup(
        self,
        lookup: DurableCheckpointLookupIndex,
    ) -> SignedDurableChainCheckpoint:
        try:
            node = self._chain.get_node(
                lookup.chain_node_hash
            )
        except Exception as exc:
            raise DurableCheckpointError(
                "indexed checkpoint registry node is unavailable"
            ) from exc
        if (
            node.kind
            != "durable.chain.checkpoint"
        ):
            raise DurableCheckpointError(
                "indexed checkpoint registry node has wrong kind"
            )
        raw_checkpoint = node.payload.get(
            "checkpoint"
        )
        raw_signature = node.payload.get(
            "signature"
        )
        if (
            not isinstance(raw_checkpoint, dict)
            or not isinstance(raw_signature, dict)
        ):
            raise DurableCheckpointError(
                "indexed checkpoint registry payload is invalid"
            )
        item = SignedDurableChainCheckpoint(
            self._checkpoint(
                dict(raw_checkpoint)
            ),
            self._signature(
                dict(raw_signature)
            ),
            node.node_hash,
        )
        expected = self._lookup_for(
            item
        )
        if expected != lookup:
            raise DurableCheckpointError(
                "indexed checkpoint identity differs from registry node"
            )
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableCheckpointError(
                "indexed checkpoint signature is invalid"
            ) from exc
        if (
            item.signature.artifact_type
            != "durable-chain-checkpoint"
            or item.signature.artifact_digest
            != item.checkpoint.digest
        ):
            raise DurableCheckpointError(
                "indexed checkpoint signature binding is invalid"
            )
        if not self._chain.root_is_ancestor(
            item.chain_node_hash
        ):
            raise DurableCheckpointError(
                "indexed checkpoint node is not committed in registry"
            )
        return item

    def find_by_digest(
        self,
        checkpoint_digest: str,
    ) -> SignedDurableChainCheckpoint | None:
        checkpoint_digest = _digest(
            "checkpoint_digest",
            checkpoint_digest,
        )
        lookup = self._lookup_record(
            self._digest_lookup_key(
                checkpoint_digest
            )
        )
        if lookup is not None:
            item = self._item_from_lookup(
                lookup
            )
            if (
                item.checkpoint.digest
                != checkpoint_digest
            ):
                raise DurableCheckpointError(
                    "indexed checkpoint differs from requested digest"
                )
            return item

        matches = tuple(
            item
            for item in self.snapshot()
            if item.checkpoint.digest
            == checkpoint_digest
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise DurableCheckpointError(
                "checkpoint digest is not unique in canonical registry"
            )
        self._index_item(
            matches[0]
        )
        return matches[0]

    def find_by_root(
        self,
        chain_id: str,
        root_hash: str,
    ) -> SignedDurableChainCheckpoint | None:
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        key = self._root_lookup_key(
            chain_id,
            root_hash,
        )
        lookup = self._lookup_record(
            key
        )
        if lookup is not None:
            if lookup.chain_id != chain_id:
                raise DurableCheckpointError(
                    "checkpoint root index chain mismatch"
                )
            item = self._item_from_lookup(
                lookup
            )
            if (
                item.checkpoint.chain_id != chain_id
                or item.checkpoint.root_hash
                != root_hash
            ):
                raise DurableCheckpointError(
                    "indexed checkpoint differs from requested root"
                )
            return item

        matches = tuple(
            item
            for item in self.snapshot()
            if (
                item.checkpoint.chain_id
                == chain_id
                and item.checkpoint.root_hash
                == root_hash
            )
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise DurableCheckpointError(
                "checkpoint root is not unique in canonical registry"
            )
        self._index_item(
            matches[0]
        )
        return matches[0]

    def inspect_lookup_indexes(
        self,
        chain_id: str,
    ) -> DurableCheckpointIndexHealth:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        registry_valid = self.verify()
        if not registry_valid:
            return DurableCheckpointIndexHealth(
                chain_id,
                DurableCheckpointIndexState.INVALID,
                False,
                0,
                0,
                0,
                (),
                (),
                (
                    "canonical checkpoint registry failed integrity",
                ),
            )

        items = tuple(
            item
            for item in self.snapshot()
            if (
                item.checkpoint.chain_id
                == chain_id
            )
        )
        missing_digest: list[str] = []
        missing_root: list[str] = []
        corrupt: list[str] = []
        digest_present = 0
        root_present = 0

        for item in items:
            expected = self._lookup_for(
                item
            )
            checks = (
                (
                    "digest",
                    self._digest_lookup_key(
                        item.checkpoint.digest
                    ),
                    item.checkpoint.digest,
                ),
                (
                    "root",
                    self._root_lookup_key(
                        chain_id,
                        item.checkpoint.root_hash,
                    ),
                    item.checkpoint.root_hash,
                ),
            )
            for (
                kind,
                key,
                identity,
            ) in checks:
                record = self._backend.get(
                    self._namespace,
                    key,
                )
                if record is None:
                    if kind == "digest":
                        missing_digest.append(
                            identity
                        )
                    else:
                        missing_root.append(
                            identity
                        )
                    continue
                if kind == "digest":
                    digest_present += 1
                else:
                    root_present += 1
                if not isinstance(
                    record.value,
                    dict,
                ):
                    corrupt.append(
                        f"{kind}:{identity}:type"
                    )
                    continue
                try:
                    actual = self._lookup(
                        dict(record.value)
                    )
                except Exception as exc:
                    corrupt.append(
                        f"{kind}:{identity}:"
                        f"{type(exc).__name__}"
                    )
                    continue
                if actual != expected:
                    corrupt.append(
                        f"{kind}:{identity}:mismatch"
                    )

        if corrupt:
            state = (
                DurableCheckpointIndexState.INVALID
            )
        elif (
            missing_digest
            or missing_root
        ):
            state = (
                DurableCheckpointIndexState.DEGRADED
            )
        else:
            state = (
                DurableCheckpointIndexState.HEALTHY
            )
        return DurableCheckpointIndexHealth(
            chain_id,
            state,
            True,
            len(items),
            digest_present,
            root_present,
            tuple(missing_digest),
            tuple(missing_root),
            tuple(corrupt),
        )

    def repair_missing_lookup_indexes(
        self,
        chain_id: str,
        *,
        max_repairs: int = 4096,
    ) -> int:
        """Repair only absent exact indexes for one chain.

        Existing malformed or conflicting records are never overwritten.
        Operators must investigate those as integrity failures rather than
        treating them as cache misses.
        """
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        if (
            isinstance(max_repairs, bool)
            or not isinstance(max_repairs, int)
            or max_repairs <= 0
        ):
            raise ValueError(
                "max_repairs must be positive integer"
            )
        health = self.inspect_lookup_indexes(
            chain_id
        )
        if not health.registry_valid:
            raise DurableCheckpointError(
                "cannot repair indexes from invalid checkpoint registry"
            )
        if health.corrupt_indexes:
            raise DurableCheckpointError(
                "cannot auto-repair conflicting checkpoint indexes"
            )
        if health.missing > max_repairs:
            raise DurableCheckpointError(
                "checkpoint index repair exceeds bounded repair limit"
            )
        if health.missing == 0:
            return 0

        by_digest = {
            item.checkpoint.digest: item
            for item in self.snapshot()
            if item.checkpoint.chain_id == chain_id
        }
        by_root = {
            item.checkpoint.root_hash: item
            for item in by_digest.values()
        }
        repaired = 0
        for digest in health.missing_digest_indexes:
            item = by_digest.get(digest)
            if item is None:
                raise DurableCheckpointError(
                    "missing digest index has no canonical checkpoint"
                )
            lookup = self._lookup_for(item)
            if self._put_lookup(
                self._digest_lookup_key(digest),
                lookup,
            ):
                repaired += 1
        for root_hash in health.missing_root_indexes:
            item = by_root.get(root_hash)
            if item is None:
                raise DurableCheckpointError(
                    "missing root index has no canonical checkpoint"
                )
            lookup = self._lookup_for(item)
            if self._put_lookup(
                self._root_lookup_key(
                    chain_id,
                    root_hash,
                ),
                lookup,
            ):
                repaired += 1

        after = self.inspect_lookup_indexes(
            chain_id
        )
        if not after.healthy:
            raise DurableCheckpointError(
                "checkpoint index repair did not restore healthy state"
            )
        return repaired

    def repair_lookup_indexes(
        self,
    ) -> int:
        if not self.verify():
            raise DurableCheckpointError(
                "cannot repair indexes from invalid checkpoint registry"
            )
        repaired = 0
        for item in self.snapshot():
            repaired += self._index_item(
                item
            )
        return repaired

    def verify_lookup_indexes(
        self,
    ) -> bool:
        if not self.verify():
            return False
        try:
            for item in self.snapshot():
                digest_item = self.find_by_digest(
                    item.checkpoint.digest
                )
                root_item = self.find_by_root(
                    item.checkpoint.chain_id,
                    item.checkpoint.root_hash,
                )
                if (
                    digest_item != item
                    or root_item != item
                ):
                    return False
        except (
            DurableCheckpointError,
            ValueError,
            TypeError,
            KeyError,
        ):
            return False
        return True

    @staticmethod
    def _checkpoint(
        raw: dict[str, object],
    ) -> DurableChainCheckpoint:
        return DurableChainCheckpoint(
            int(raw["schema_version"]),
            str(raw["chain_id"]),
            int(raw["sequence"]),
            str(raw["root_hash"]),
            str(
                raw.get(
                    "previous_checkpoint_digest",
                    "",
                )
            ),
            float(raw["observed_at"]),
        )

    @staticmethod
    def _signature(
        raw: dict[str, object],
    ) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    def snapshot(
        self,
    ) -> tuple[SignedDurableChainCheckpoint, ...]:
        result = []
        for node in self._chain.snapshot():
            raw_checkpoint = node.payload.get(
                "checkpoint"
            )
            raw_signature = node.payload.get(
                "signature"
            )
            if (
                not isinstance(raw_checkpoint, dict)
                or not isinstance(raw_signature, dict)
            ):
                raise EvidenceCorruption(
                    "durable checkpoint payload is invalid"
                )
            result.append(
                SignedDurableChainCheckpoint(
                    self._checkpoint(
                        dict(raw_checkpoint)
                    ),
                    self._signature(
                        dict(raw_signature)
                    ),
                    node.node_hash,
                )
            )
        return tuple(result)

    def for_chain(
        self,
        chain_id: str,
    ) -> tuple[SignedDurableChainCheckpoint, ...]:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        return tuple(
            item
            for item in self.snapshot()
            if item.checkpoint.chain_id == chain_id
        )

    def latest(
        self,
        chain_id: str,
    ) -> SignedDurableChainCheckpoint | None:
        items = self.for_chain(chain_id)
        return items[-1] if items else None

    def publish(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
    ) -> SignedDurableChainCheckpoint:
        if not chain_id or len(chain_id) > 128:
            raise ValueError("invalid chain_id")
        if not isinstance(
            chain,
            CheckpointableEvidenceChain,
        ):
            raise TypeError(
                "chain does not support durable checkpoint verification"
            )
        if not chain.verify():
            raise DurableCheckpointError(
                "cannot checkpoint an invalid evidence chain"
            )

        head = chain.head()
        sequence = int(head.sequence)
        root_hash = _digest(
            "root_hash",
            str(head.root_hash),
        )
        if not chain.verify_root(root_hash):
            raise DurableCheckpointError(
                "current evidence root failed historical verification"
            )
        if not chain.root_is_ancestor(root_hash):
            raise DurableCheckpointError(
                "current evidence root is not committed"
            )

        previous = self.latest(chain_id)
        if previous is not None:
            prior = previous.checkpoint
            if (
                prior.sequence == sequence
                and prior.root_hash == root_hash
            ):
                self._index_item(
                    previous
                )
                return previous
            if sequence <= prior.sequence:
                raise DurableCheckpointError(
                    "durable checkpoint sequence may only advance"
                )
            if not chain.root_is_ancestor(
                prior.root_hash
            ):
                raise DurableCheckpointError(
                    "previous checkpoint root is no longer a committed ancestor"
                )
            previous_digest = prior.digest
        else:
            previous_digest = ""

        observed_at = self._clock()
        checkpoint = DurableChainCheckpoint(
            1,
            chain_id,
            sequence,
            root_hash,
            previous_digest,
            observed_at,
        )
        signature = self.signer.sign(
            "durable-chain-checkpoint",
            checkpoint.digest,
            metadata={
                "chain_id": chain_id,
                "sequence": sequence,
            },
        )
        node = self._chain.append(
            "durable.chain.checkpoint",
            {
                "checkpoint": checkpoint.to_dict(),
                "signature": signature.to_dict(),
            },
        )
        item = SignedDurableChainCheckpoint(
            checkpoint,
            signature,
            node.node_hash,
        )
        self._index_item(
            item
        )
        return item

    def verify(self) -> bool:
        if not self._chain.verify():
            return False
        try:
            items = self.snapshot()
        except (
            EvidenceCorruption,
            ValueError,
            TypeError,
            KeyError,
        ):
            return False
        latest_by_chain: dict[
            str,
            SignedDurableChainCheckpoint,
        ] = {}
        for item in items:
            checkpoint = item.checkpoint
            if (
                item.signature.artifact_type
                != "durable-chain-checkpoint"
            ):
                return False
            if (
                item.signature.artifact_digest
                != checkpoint.digest
            ):
                return False
            try:
                self.signer.verify(
                    item.signature
                )
            except ArtifactSignatureError:
                return False
            previous = latest_by_chain.get(
                checkpoint.chain_id
            )
            if previous is None:
                if checkpoint.previous_checkpoint_digest:
                    return False
            else:
                if (
                    checkpoint.previous_checkpoint_digest
                    != previous.checkpoint.digest
                ):
                    return False
                if (
                    checkpoint.sequence
                    <= previous.checkpoint.sequence
                ):
                    return False
            latest_by_chain[
                checkpoint.chain_id
            ] = item
        return True

    def inspect(
        self,
        item: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCheckpointVerification:
        if not isinstance(
            item,
            SignedDurableChainCheckpoint,
        ):
            raise TypeError(
                "item must be SignedDurableChainCheckpoint"
            )
        reasons: list[str] = []
        if not self._chain.verify():
            reasons.append(
                "checkpoint registry chain failed integrity"
            )
        else:
            try:
                canonical = next(
                    (
                        current
                        for current in self.snapshot()
                        if (
                            current.chain_node_hash
                            == item.chain_node_hash
                            and current.checkpoint.digest
                            == item.checkpoint.digest
                            and current.signature
                            == item.signature
                        )
                    ),
                    None,
                )
            except (
                EvidenceCorruption,
                ValueError,
                TypeError,
                KeyError,
            ):
                canonical = None
                reasons.append(
                    "checkpoint registry could not be reconstructed"
                )
            if canonical is None:
                reasons.append(
                    "checkpoint is not committed in canonical registry"
                )
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError:
            reasons.append(
                "checkpoint signature is invalid"
            )
        if (
            item.signature.artifact_type
            != "durable-chain-checkpoint"
        ):
            reasons.append(
                "checkpoint artifact type is invalid"
            )
        if (
            item.signature.artifact_digest
            != item.checkpoint.digest
        ):
            reasons.append(
                "checkpoint signature digest differs from checkpoint"
            )

        head = chain.head()
        current_sequence = int(
            head.sequence
        )
        current_root = _digest(
            "current_root",
            str(head.root_hash),
        )
        try:
            historical = chain.snapshot_at(
                item.checkpoint.root_hash
            )
            historical_sequence = (
                0
                if not historical
                else int(
                    historical[-1].sequence
                )
            )
            root_valid = chain.verify_root(
                item.checkpoint.root_hash
            )
            ancestor = chain.root_is_ancestor(
                item.checkpoint.root_hash
            )
        except Exception as exc:
            historical_sequence = -1
            root_valid = False
            ancestor = False
            reasons.append(
                "historical checkpoint root lookup failed: "
                f"{type(exc).__name__}"
            )

        if historical_sequence != item.checkpoint.sequence:
            reasons.append(
                "checkpoint sequence differs from historical root"
            )
        if not root_valid:
            reasons.append(
                "checkpoint root failed integrity verification"
            )
        if not ancestor:
            reasons.append(
                "checkpoint root is not a committed ancestor"
            )
        if (
            item.checkpoint.sequence
            > current_sequence
        ):
            reasons.append(
                "checkpoint sequence is ahead of current chain"
            )

        return DurableCheckpointVerification(
            not reasons,
            item.checkpoint.chain_id,
            item.checkpoint.sequence,
            item.checkpoint.root_hash,
            current_sequence,
            current_root,
            ancestor,
            tuple(reasons),
        )

    def require(
        self,
        item: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> DurableCheckpointVerification:
        report = self.inspect(
            item,
            chain,
        )
        if not report.valid:
            raise DurableCheckpointError(
                "; ".join(report.reasons)
            )
        return report

    def root_hash(self) -> str:
        return self._chain.root_hash()

    def length(self) -> int:
        return self._chain.length()
