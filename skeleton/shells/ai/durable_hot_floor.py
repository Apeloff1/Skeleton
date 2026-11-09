"""Signed monotonic hot-tier floors for compacted durable evidence chains.

A hot floor is the smallest sequence/root boundary that a live evidence chain
is allowed to trust after an older prefix has been archived and pruned from
hot storage.  It is not execution authority and it is not archival evidence by
itself.  The destructive compaction path must first prove archive coverage and
obtain a separate pruning authorization.

The floor is signed because accepting a forged floor would let a compromised
state backend skip arbitrary history during live-chain verification.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_HASH = "0" * 64


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


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


@dataclass(frozen=True)
class DurableHotFloor:
    schema_version: int
    floor_id: str
    chain_id: str
    sequence: int
    root_hash: str
    previous_sequence: int
    previous_root_hash: str
    archive_id: str
    archive_manifest_digest: str
    compaction_certificate_id: str
    pruning_authorization_id: str
    operation_id: str
    committed_at: float
    fencing_token: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported hot floor schema")
        object.__setattr__(
            self,
            "floor_id",
            _digest("floor_id", self.floor_id),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "root_hash",
            "previous_root_hash",
            "archive_manifest_digest",
            "compaction_certificate_id",
            "pruning_authorization_id",
            "operation_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        for name in (
            "sequence",
            "previous_sequence",
            "fencing_token",
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
        if self.sequence <= 0:
            raise ValueError("hot floor sequence must be positive")
        if self.fencing_token <= 0:
            raise ValueError("hot floor fencing token must be positive")
        if self.previous_sequence >= self.sequence:
            raise ValueError(
                "hot floor must advance beyond previous sequence"
            )
        if (
            self.previous_sequence == 0
            and self.previous_root_hash != GENESIS_HASH
        ):
            raise ValueError(
                "genesis previous floor must use genesis hash"
            )
        if (
            self.previous_sequence > 0
            and self.previous_root_hash == GENESIS_HASH
        ):
            raise ValueError(
                "non-genesis previous floor may not use genesis hash"
            )
        if self.root_hash == GENESIS_HASH:
            raise ValueError(
                "non-genesis hot floor may not use genesis hash"
            )
        if (
            isinstance(self.committed_at, bool)
            or not isinstance(self.committed_at, (int, float))
            or not math.isfinite(float(self.committed_at))
            or float(self.committed_at) < 0.0
        ):
            raise ValueError(
                "committed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "committed_at",
            float(self.committed_at),
        )

    @staticmethod
    def derive_id(
        *,
        chain_id: str,
        sequence: int,
        root_hash: str,
        previous_sequence: int,
        previous_root_hash: str,
        archive_id: str,
        archive_manifest_digest: str,
        compaction_certificate_id: str,
        pruning_authorization_id: str,
        operation_id: str,
        committed_at: float,
        fencing_token: int,
    ) -> str:
        payload = {
            "chain_id": chain_id,
            "sequence": sequence,
            "root_hash": root_hash,
            "previous_sequence": previous_sequence,
            "previous_root_hash": previous_root_hash,
            "archive_id": archive_id,
            "archive_manifest_digest": archive_manifest_digest,
            "compaction_certificate_id": compaction_certificate_id,
            "pruning_authorization_id": pruning_authorization_id,
            "operation_id": operation_id,
            "committed_at": float(committed_at),
            "fencing_token": fencing_token,
            "authority": "signed-hot-tier-floor",
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "floor_id": self.floor_id,
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "previous_sequence": self.previous_sequence,
            "previous_root_hash": self.previous_root_hash,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "compaction_certificate_id": self.compaction_certificate_id,
            "pruning_authorization_id": self.pruning_authorization_id,
            "operation_id": self.operation_id,
            "committed_at": self.committed_at,
            "fencing_token": self.fencing_token,
            "authority": "signed-hot-tier-floor",
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.unsigned_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableHotFloor:
    floor: DurableHotFloor
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.floor,
            DurableHotFloor,
        ):
            raise TypeError("floor must be DurableHotFloor")
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    @property
    def floor_id(self) -> str:
        return self.floor.floor_id

    @property
    def sequence(self) -> int:
        return self.floor.sequence

    @property
    def root_hash(self) -> str:
        return self.floor.root_hash

    def to_dict(self) -> dict[str, object]:
        return {
            "floor": self.floor.to_dict(),
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class HotFloorPosition:
    sequence: int
    root_hash: str
    floor_id: str = ""
    archive_id: str = ""
    archive_manifest_digest: str = ""
    operation_id: str = ""
    fencing_token: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError(
                "hot floor sequence must be non-negative"
            )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        for name in (
            "floor_id",
            "archive_manifest_digest",
            "operation_id",
        ):
            value = getattr(self, name)
            if value:
                object.__setattr__(
                    self,
                    name,
                    _digest(name, value),
                )
        if self.archive_id:
            _identity(
                "archive_id",
                self.archive_id,
                maximum=256,
            )
        if (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or self.fencing_token < 0
        ):
            raise ValueError(
                "hot floor fencing_token must be non-negative"
            )
        if self.sequence == 0:
            if self.root_hash != GENESIS_HASH:
                raise ValueError(
                    "genesis hot floor must use genesis hash"
                )
            if any(
                (
                    self.floor_id,
                    self.archive_id,
                    self.archive_manifest_digest,
                    self.operation_id,
                    self.fencing_token,
                )
            ):
                raise ValueError(
                    "genesis hot floor may not carry authority metadata"
                )
        else:
            if not self.floor_id:
                raise ValueError(
                    "non-genesis hot floor requires floor_id"
                )
            if not self.archive_id:
                raise ValueError(
                    "non-genesis hot floor requires archive_id"
                )
            if not self.archive_manifest_digest:
                raise ValueError(
                    "non-genesis hot floor requires archive manifest"
                )
            if not self.operation_id:
                raise ValueError(
                    "non-genesis hot floor requires operation_id"
                )
            if self.fencing_token <= 0:
                raise ValueError(
                    "non-genesis hot floor requires fencing token"
                )

    @classmethod
    def genesis(cls) -> "HotFloorPosition":
        return cls(0, GENESIS_HASH)

    @classmethod
    def from_signed(
        cls,
        item: SignedDurableHotFloor,
    ) -> "HotFloorPosition":
        return cls(
            item.floor.sequence,
            item.floor.root_hash,
            item.floor.floor_id,
            item.floor.archive_id,
            item.floor.archive_manifest_digest,
            item.floor.operation_id,
            item.floor.fencing_token,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "floor_id": self.floor_id,
            "archive_id": self.archive_id,
            "archive_manifest_digest": self.archive_manifest_digest,
            "operation_id": self.operation_id,
            "fencing_token": self.fencing_token,
        }


@dataclass(frozen=True)
class DurableHotFloorHistoryIndex:
    chain_id: str
    sequence: int
    root_hash: str
    floor_id: str

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "hot floor history sequence must be positive"
            )
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        object.__setattr__(
            self,
            "floor_id",
            _digest("floor_id", self.floor_id),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "floor_id": self.floor_id,
        }


@dataclass(frozen=True)
class DurableHotFloorHistoryReport:
    chain_id: str
    floors: tuple[SignedDurableHotFloor, ...]
    current_floor_id: str
    current_sequence: int
    current_root: str
    complete_to_genesis: bool
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        floors = tuple(self.floors)
        object.__setattr__(
            self,
            "floors",
            floors,
        )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )
        if floors:
            if (
                not self.current_floor_id
                or len(self.current_floor_id) != 64
            ):
                raise ValueError(
                    "history report requires current floor id"
                )
            if (
                isinstance(self.current_sequence, bool)
                or not isinstance(self.current_sequence, int)
                or self.current_sequence <= 0
            ):
                raise ValueError(
                    "history current_sequence must be positive"
                )
            _digest(
                "current_root",
                self.current_root,
            )
        else:
            if self.current_floor_id:
                raise ValueError(
                    "empty history may not carry current floor id"
                )
            if self.current_sequence != 0:
                raise ValueError(
                    "empty history must use sequence zero"
                )
            if self.current_root != GENESIS_HASH:
                raise ValueError(
                    "empty history must use genesis root"
                )
        if not isinstance(
            self.complete_to_genesis,
            bool,
        ):
            raise ValueError(
                "complete_to_genesis must be bool"
            )
        if any(
            not isinstance(issue, str)
            or not issue
            or len(issue) > 2048
            for issue in self.issues
        ):
            raise ValueError(
                "invalid hot floor history issue"
            )

    @property
    def ok(self) -> bool:
        return (
            self.complete_to_genesis
            and not self.issues
        )

    @property
    def floor_count(self) -> int:
        return len(self.floors)

    @property
    def oldest_sequence(self) -> int:
        if not self.floors:
            return 0
        return self.floors[0].floor.sequence

    @property
    def newest_sequence(self) -> int:
        if not self.floors:
            return 0
        return self.floors[-1].floor.sequence

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
            "floor_count": self.floor_count,
            "oldest_sequence": self.oldest_sequence,
            "newest_sequence": self.newest_sequence,
            "current_floor_id": self.current_floor_id,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "complete_to_genesis": (
                self.complete_to_genesis
            ),
            "floors": [
                item.to_dict()
                for item in self.floors
            ],
            "issues": list(self.issues),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableHotFloorError(RuntimeError):
    pass


class DurableHotFloorStore:
    """Signed monotonic floor registry for one or more durable chains."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-hot-floors",
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
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError("signer must be ArtifactSigner")
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid hot floor namespace"
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
            raise TypeError("clock must be callable")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _history_key(floor_id: str) -> str:
        return (
            "history:"
            + _digest(
                "floor_id",
                floor_id,
            )
        )

    @staticmethod
    def _sequence_key(
        chain_id: str,
        sequence: int,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError(
                "sequence must be positive integer"
            )
        return (
            "history-sequence:"
            + hashlib.sha256(
                chain_id.encode()
            ).hexdigest()
            + f":{sequence:020d}"
        )

    @staticmethod
    def _key(chain_id: str) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        return (
            "floor:"
            + hashlib.sha256(
                chain_id.encode()
            ).hexdigest()
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

    @classmethod
    def _signed(
        cls,
        raw: dict[str, object],
    ) -> SignedDurableHotFloor:
        floor_raw = raw.get("floor")
        signature_raw = raw.get("signature")
        if not isinstance(floor_raw, dict):
            raise DurableHotFloorError(
                "hot floor record has invalid floor shape"
            )
        if not isinstance(signature_raw, dict):
            raise DurableHotFloorError(
                "hot floor record has invalid signature shape"
            )
        floor = DurableHotFloor(
            int(floor_raw["schema_version"]),
            str(floor_raw["floor_id"]),
            str(floor_raw["chain_id"]),
            int(floor_raw["sequence"]),
            str(floor_raw["root_hash"]),
            int(floor_raw["previous_sequence"]),
            str(floor_raw["previous_root_hash"]),
            str(floor_raw["archive_id"]),
            str(floor_raw["archive_manifest_digest"]),
            str(floor_raw["compaction_certificate_id"]),
            str(floor_raw["pruning_authorization_id"]),
            str(floor_raw["operation_id"]),
            float(floor_raw["committed_at"]),
            int(floor_raw["fencing_token"]),
        )
        return SignedDurableHotFloor(
            floor,
            cls._signature(signature_raw),
        )

    def _verify(
        self,
        item: SignedDurableHotFloor,
    ) -> None:
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise DurableHotFloorError(
                "hot floor signature verification failed"
            ) from exc
        if (
            item.signature.artifact_type
            != "durable-hot-floor"
        ):
            raise DurableHotFloorError(
                "unexpected hot floor artifact type"
            )
        if (
            item.signature.artifact_digest
            != item.floor.digest
        ):
            raise DurableHotFloorError(
                "hot floor signature digest mismatch"
            )
        metadata = dict(
            item.signature.metadata
        )
        if (
            metadata.get("floor_id")
            != item.floor.floor_id
            or metadata.get("chain_id")
            != item.floor.chain_id
        ):
            raise DurableHotFloorError(
                "hot floor signature metadata mismatch"
            )

    def _persist_committed(
        self,
        item: SignedDurableHotFloor,
    ) -> None:
        """Persist immutable history for a floor already known to be current."""
        if not isinstance(
            item,
            SignedDurableHotFloor,
        ):
            raise TypeError(
                "item must be SignedDurableHotFloor"
            )
        self._verify(item)
        payload = item.to_dict()
        history_key = self._history_key(
            item.floor.floor_id
        )
        history = self.backend.get(
            self.namespace,
            history_key,
        )
        if history is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    history_key,
                    payload,
                )
            except DistributedStateConflict:
                history = self.backend.get(
                    self.namespace,
                    history_key,
                )
        if history is None:
            history = self.backend.get(
                self.namespace,
                history_key,
            )
        if (
            history is None
            or not isinstance(history.value, dict)
        ):
            raise DurableHotFloorError(
                "hot floor history record is missing or invalid"
            )
        historical = self._signed(
            dict(history.value)
        )
        self._verify(historical)
        if historical != item:
            raise DurableHotFloorError(
                "hot floor history id binds different signed floor"
            )

        index = DurableHotFloorHistoryIndex(
            item.floor.chain_id,
            item.floor.sequence,
            item.floor.root_hash,
            item.floor.floor_id,
        )
        index_key = self._sequence_key(
            item.floor.chain_id,
            item.floor.sequence,
        )
        existing = self.backend.get(
            self.namespace,
            index_key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    index_key,
                    index.to_dict(),
                )
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    index_key,
                )
        if existing is None:
            existing = self.backend.get(
                self.namespace,
                index_key,
            )
        if (
            existing is None
            or not isinstance(existing.value, dict)
        ):
            raise DurableHotFloorError(
                "hot floor history sequence index is missing or invalid"
            )
        raw = dict(existing.value)
        indexed = DurableHotFloorHistoryIndex(
            str(raw["chain_id"]),
            int(raw["sequence"]),
            str(raw["root_hash"]),
            str(raw["floor_id"]),
        )
        if indexed != index:
            raise DurableHotFloorError(
                "hot floor history sequence already binds different floor"
            )

    def get(
        self,
        floor_id: str,
    ) -> SignedDurableHotFloor | None:
        floor_id = _digest(
            "floor_id",
            floor_id,
        )
        record = self.backend.get(
            self.namespace,
            self._history_key(floor_id),
        )
        if record is not None:
            if not isinstance(record.value, dict):
                raise DurableHotFloorError(
                    "hot floor history record must be mapping"
                )
            item = self._signed(
                dict(record.value)
            )
            if item.floor.floor_id != floor_id:
                raise DurableHotFloorError(
                    "hot floor history identity mismatch"
                )
            self._verify(item)
            return item

        # Repair the post-CAS/pre-history crash window from the authoritative
        # current record.  This never promotes an orphan candidate because
        # only the current key establishes committed authority.
        # Floor ids are globally content-addressed; scan is deliberately
        # avoided.  A caller that knows the chain can use floor_at(), which
        # can repair from the current record.  Direct get returns absent here.
        return None

    def floor_at(
        self,
        chain_id: str,
        sequence: int,
    ) -> SignedDurableHotFloor | None:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError(
                "sequence must be positive integer"
            )
        index_key = self._sequence_key(
            chain_id,
            sequence,
        )
        record = self.backend.get(
            self.namespace,
            index_key,
        )
        if record is not None:
            if not isinstance(record.value, dict):
                raise DurableHotFloorError(
                    "hot floor history sequence index must be mapping"
                )
            raw = dict(record.value)
            index = DurableHotFloorHistoryIndex(
                str(raw["chain_id"]),
                int(raw["sequence"]),
                str(raw["root_hash"]),
                str(raw["floor_id"]),
            )
            if (
                index.chain_id != chain_id
                or index.sequence != sequence
            ):
                raise DurableHotFloorError(
                    "hot floor history sequence index identity mismatch"
                )
            item = self.get(index.floor_id)
            if item is None:
                raise DurableHotFloorError(
                    "hot floor sequence index references missing history"
                )
            if (
                item.floor.chain_id != chain_id
                or item.floor.sequence != sequence
                or item.floor.root_hash != index.root_hash
            ):
                raise DurableHotFloorError(
                    "hot floor history index/content mismatch"
                )
            return item

        current = self.current(chain_id)
        if (
            current is not None
            and current.floor.sequence == sequence
        ):
            self._persist_committed(current)
            return current
        return None

    def current(
        self,
        chain_id: str,
    ) -> SignedDurableHotFloor | None:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        record = self.backend.get(
            self.namespace,
            self._key(chain_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, dict):
            raise DurableHotFloorError(
                "hot floor record must be mapping"
            )
        item = self._signed(
            dict(record.value)
        )
        if item.floor.chain_id != chain_id:
            raise DurableHotFloorError(
                "hot floor chain identity mismatch"
            )
        self._verify(item)
        return item

    def position(
        self,
        chain_id: str,
    ) -> HotFloorPosition:
        current = self.current(chain_id)
        if current is None:
            return HotFloorPosition.genesis()
        return HotFloorPosition.from_signed(
            current
        )

    def advance(
        self,
        *,
        chain_id: str,
        sequence: int,
        root_hash: str,
        archive_id: str,
        archive_manifest_digest: str,
        compaction_certificate_id: str,
        pruning_authorization_id: str,
        operation_id: str,
        fencing_token: int,
        expected_previous_sequence: int | None = None,
        expected_previous_root: str = "",
    ) -> SignedDurableHotFloor:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        root_hash = _digest(
            "root_hash",
            root_hash,
        )
        archive_manifest_digest = _digest(
            "archive_manifest_digest",
            archive_manifest_digest,
        )
        compaction_certificate_id = _digest(
            "compaction_certificate_id",
            compaction_certificate_id,
        )
        pruning_authorization_id = _digest(
            "pruning_authorization_id",
            pruning_authorization_id,
        )
        operation_id = _digest(
            "operation_id",
            operation_id,
        )
        _identity(
            "archive_id",
            archive_id,
            maximum=256,
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError(
                "sequence must be positive integer"
            )
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or fencing_token <= 0
        ):
            raise ValueError(
                "fencing_token must be positive integer"
            )
        if expected_previous_sequence is not None and (
            isinstance(expected_previous_sequence, bool)
            or not isinstance(
                expected_previous_sequence,
                int,
            )
            or expected_previous_sequence < 0
        ):
            raise ValueError(
                "expected_previous_sequence must be non-negative"
            )
        if expected_previous_root:
            expected_previous_root = _digest(
                "expected_previous_root",
                expected_previous_root,
            )

        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(float(now))
            or float(now) < 0.0
        ):
            raise DurableHotFloorError(
                "hot floor clock returned invalid time"
            )
        now = float(now)

        key = self._key(chain_id)
        for _ in range(self.max_cas_retries):
            record = self.backend.get(
                self.namespace,
                key,
            )
            revision = (
                0
                if record is None
                else record.revision
            )
            current = (
                None
                if record is None
                else self._signed(
                    dict(record.value)
                )
            )
            if current is not None:
                self._verify(current)
                if current.floor.chain_id != chain_id:
                    raise DurableHotFloorError(
                        "hot floor current chain mismatch"
                    )
                self._persist_committed(current)
                previous_sequence = (
                    current.floor.sequence
                )
                previous_root = (
                    current.floor.root_hash
                )
            else:
                previous_sequence = 0
                previous_root = GENESIS_HASH

            if (
                expected_previous_sequence is not None
                and previous_sequence
                != expected_previous_sequence
            ):
                raise DurableHotFloorError(
                    "hot floor previous sequence changed"
                )
            if (
                expected_previous_root
                and previous_root
                != expected_previous_root
            ):
                raise DurableHotFloorError(
                    "hot floor previous root changed"
                )
            if sequence < previous_sequence:
                raise DurableHotFloorError(
                    "hot floor cannot move backwards"
                )
            if (
                current is not None
                and sequence > previous_sequence
                and fencing_token
                <= current.floor.fencing_token
            ):
                raise DurableHotFloorError(
                    "hot floor fencing token must increase"
                )
            if sequence == previous_sequence:
                if (
                    current is not None
                    and current.floor.root_hash
                    == root_hash
                    and current.floor.archive_id
                    == archive_id
                    and current.floor.archive_manifest_digest
                    == archive_manifest_digest
                    and current.floor.compaction_certificate_id
                    == compaction_certificate_id
                    and current.floor.pruning_authorization_id
                    == pruning_authorization_id
                    and current.floor.operation_id
                    == operation_id
                ):
                    self._persist_committed(current)
                    return current
                raise DurableHotFloorError(
                    "same hot floor sequence carries different authority"
                )

            floor_id = DurableHotFloor.derive_id(
                chain_id=chain_id,
                sequence=sequence,
                root_hash=root_hash,
                previous_sequence=previous_sequence,
                previous_root_hash=previous_root,
                archive_id=archive_id,
                archive_manifest_digest=archive_manifest_digest,
                compaction_certificate_id=compaction_certificate_id,
                pruning_authorization_id=pruning_authorization_id,
                operation_id=operation_id,
                committed_at=now,
                fencing_token=fencing_token,
            )
            floor = DurableHotFloor(
                1,
                floor_id,
                chain_id,
                sequence,
                root_hash,
                previous_sequence,
                previous_root,
                archive_id,
                archive_manifest_digest,
                compaction_certificate_id,
                pruning_authorization_id,
                operation_id,
                now,
                fencing_token,
            )
            signature = self.signer.sign(
                "durable-hot-floor",
                floor.digest,
                metadata={
                    "floor_id": floor.floor_id,
                    "chain_id": chain_id,
                    "operation_id": operation_id,
                    "authority": "signed-hot-tier-floor",
                },
            )
            item = SignedDurableHotFloor(
                floor,
                signature,
            )
            try:
                stored = (
                    self.backend.put_if_absent(
                        self.namespace,
                        key,
                        item.to_dict(),
                    )
                    if revision == 0
                    else self.backend.compare_and_swap(
                        self.namespace,
                        key,
                        expected_revision=revision,
                        value=item.to_dict(),
                    )
                )
                if stored.revision <= 0:
                    raise DurableHotFloorError(
                        "hot floor backend returned invalid revision"
                    )
                self._persist_committed(item)
                return item
            except DistributedStateConflict:
                continue
        raise DurableHotFloorError(
            "hot floor CAS retry budget exhausted"
        )

    def inspect_history(
        self,
        chain_id: str,
        *,
        max_floors: int = 1024,
    ) -> DurableHotFloorHistoryReport:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        if (
            isinstance(max_floors, bool)
            or not isinstance(max_floors, int)
            or max_floors <= 0
        ):
            raise ValueError(
                "max_floors must be positive integer"
            )
        current = self.current(chain_id)
        if current is None:
            return DurableHotFloorHistoryReport(
                chain_id,
                (),
                "",
                0,
                GENESIS_HASH,
                True,
                (),
            )

        reverse: list[
            SignedDurableHotFloor
        ] = []
        issues: list[str] = []
        seen_ids: set[str] = set()
        cursor = current
        complete = False

        for _ in range(max_floors):
            floor = cursor.floor
            if floor.floor_id in seen_ids:
                issues.append(
                    "hot floor history contains a cycle"
                )
                break
            seen_ids.add(floor.floor_id)
            reverse.append(cursor)

            if floor.previous_sequence == 0:
                if (
                    floor.previous_root_hash
                    != GENESIS_HASH
                ):
                    issues.append(
                        "oldest hot floor does not terminate at genesis root"
                    )
                else:
                    complete = True
                break

            try:
                previous = self.floor_at(
                    chain_id,
                    floor.previous_sequence,
                )
            except Exception as exc:
                issues.append(
                    "historical floor lookup raised "
                    f"{type(exc).__name__}"
                )
                break
            if previous is None:
                issues.append(
                    "historical floor is missing at previous sequence"
                )
                break
            previous_floor = previous.floor
            if (
                previous_floor.root_hash
                != floor.previous_root_hash
            ):
                issues.append(
                    "historical floor root does not match successor previous root"
                )
                break
            if (
                previous_floor.sequence
                >= floor.sequence
            ):
                issues.append(
                    "historical floor sequence is not strictly increasing"
                )
                break
            if (
                previous_floor.fencing_token
                >= floor.fencing_token
            ):
                issues.append(
                    "hot floor fencing token is not strictly increasing"
                )
                break
            if (
                previous_floor.committed_at
                > floor.committed_at
            ):
                issues.append(
                    "hot floor commit time moves backwards"
                )
                break
            cursor = previous
        else:
            issues.append(
                "hot floor history exceeds traversal bound"
            )

        floors = tuple(reversed(reverse))
        return DurableHotFloorHistoryReport(
            chain_id,
            floors,
            current.floor.floor_id,
            current.floor.sequence,
            current.floor.root_hash,
            complete,
            tuple(issues),
        )

    def require_history(
        self,
        chain_id: str,
        *,
        max_floors: int = 1024,
    ) -> DurableHotFloorHistoryReport:
        report = self.inspect_history(
            chain_id,
            max_floors=max_floors,
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "hot floor history is incomplete"
            )
            raise DurableHotFloorError(
                detail
            )
        return report

    def require_position(
        self,
        chain_id: str,
        *,
        sequence: int,
        root_hash: str,
    ) -> SignedDurableHotFloor:
        current = self.current(chain_id)
        if current is None:
            raise DurableHotFloorError(
                "required hot floor is missing"
            )
        if (
            current.floor.sequence != sequence
            or current.floor.root_hash
            != _digest("root_hash", root_hash)
        ):
            raise DurableHotFloorError(
                "hot floor differs from required position"
            )
        return current
