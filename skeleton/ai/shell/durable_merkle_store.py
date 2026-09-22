"""Immutable CAS storage for finalized-session Merkle proof bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
)
from skeleton.shells.ai.durable_merkle_session import (
    DurableSessionMerkleProofBundle,
)
from skeleton.shells.ai.store_protocol import (
    VersionedStateBackend,
)


def _digest(
    name: str,
    value: str,
) -> str:
    if len(value) != 64:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
    return value.lower()


def _identity(
    name: str,
    value: str,
    maximum: int,
) -> str:
    if not value or len(value) > maximum:
        raise ValueError(
            f"invalid {name}"
        )
    return value


@dataclass(frozen=True)
class DurableMerkleBundleIndex:
    finalization_id: str
    session_id: str
    bundle_digest: str
    recovery_checkpoint_digest: str
    session_integrity_digest: str
    journal_checkpoint_digest: str
    receipt_checkpoint_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                256,
            ),
        )
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                160,
            ),
        )
        for name in (
            "bundle_digest",
            "recovery_checkpoint_digest",
            "session_integrity_digest",
            "journal_checkpoint_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        if self.receipt_checkpoint_digest:
            object.__setattr__(
                self,
                "receipt_checkpoint_digest",
                _digest(
                    "receipt_checkpoint_digest",
                    self.receipt_checkpoint_digest,
                ),
            )

    @classmethod
    def from_bundle(
        cls,
        bundle: DurableSessionMerkleProofBundle,
    ) -> "DurableMerkleBundleIndex":
        if not isinstance(
            bundle,
            DurableSessionMerkleProofBundle,
        ):
            raise TypeError(
                "bundle must be DurableSessionMerkleProofBundle"
            )
        return cls(
            bundle.finalization_id,
            bundle.session_id,
            bundle.digest,
            bundle.recovery_checkpoint_digest,
            bundle.session_integrity_digest,
            bundle.journal_checkpoint.digest,
            (
                ""
                if bundle.receipt_checkpoint
                is None
                else bundle.receipt_checkpoint.digest
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "finalization_id": (
                self.finalization_id
            ),
            "session_id": self.session_id,
            "bundle_digest": (
                self.bundle_digest
            ),
            "recovery_checkpoint_digest": (
                self.recovery_checkpoint_digest
            ),
            "session_integrity_digest": (
                self.session_integrity_digest
            ),
            "journal_checkpoint_digest": (
                self.journal_checkpoint_digest
            ),
            "receipt_checkpoint_digest": (
                self.receipt_checkpoint_digest
            ),
        }


@dataclass(frozen=True)
class StoredDurableMerkleBundle:
    revision: int
    bundle: DurableSessionMerkleProofBundle

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(
                self.revision,
                int,
            )
            or self.revision <= 0
        ):
            raise ValueError(
                "bundle revision must be positive integer"
            )
        if not isinstance(
            self.bundle,
            DurableSessionMerkleProofBundle,
        ):
            raise TypeError(
                "bundle must be DurableSessionMerkleProofBundle"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "bundle": self.bundle.to_dict(),
        }


@dataclass(frozen=True)
class StoredDurableMerkleBundleIndex:
    revision: int
    index: DurableMerkleBundleIndex

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(
                self.revision,
                int,
            )
            or self.revision <= 0
        ):
            raise ValueError(
                "index revision must be positive integer"
            )
        if not isinstance(
            self.index,
            DurableMerkleBundleIndex,
        ):
            raise TypeError(
                "index must be DurableMerkleBundleIndex"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "index": self.index.to_dict(),
        }


@dataclass(frozen=True)
class DurableMerkleBundleCommit:
    stored: StoredDurableMerkleBundle
    index: StoredDurableMerkleBundleIndex
    bundle_created: bool
    index_created: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.stored,
            StoredDurableMerkleBundle,
        ):
            raise TypeError(
                "stored must be StoredDurableMerkleBundle"
            )
        if not isinstance(
            self.index,
            StoredDurableMerkleBundleIndex,
        ):
            raise TypeError(
                "index must be StoredDurableMerkleBundleIndex"
            )
        if not isinstance(
            self.bundle_created,
            bool,
        ):
            raise ValueError(
                "bundle_created must be bool"
            )
        if not isinstance(
            self.index_created,
            bool,
        ):
            raise ValueError(
                "index_created must be bool"
            )
        if (
            self.stored.bundle.digest
            != self.index.index.bundle_digest
        ):
            raise ValueError(
                "bundle commit index digest mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "index": self.index.to_dict(),
            "bundle_created": (
                self.bundle_created
            ),
            "index_created": (
                self.index_created
            ),
        }


class DurableMerkleBundleStoreError(
    RuntimeError
):
    pass


class DurableMerkleBundleConflict(
    DurableMerkleBundleStoreError
):
    pass


class DurableMerkleBundleCorruption(
    DurableMerkleBundleStoreError
):
    pass


class DurableSessionMerkleBundleStore:
    """Store immutable proof bundles and one immutable index per finalization."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = (
            "shell-ai-durable-merkle-bundles"
        ),
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid Merkle bundle namespace"
            )
        self.backend = backend
        self.namespace = namespace

    @staticmethod
    def _bundle_key(
        bundle_digest: str,
    ) -> str:
        bundle_digest = _digest(
            "bundle_digest",
            bundle_digest,
        )
        return f"bundle:{bundle_digest}"

    @staticmethod
    def _finalization_key(
        finalization_id: str,
    ) -> str:
        finalization_id = _identity(
            "finalization_id",
            finalization_id,
            256,
        )
        return (
            "finalization:"
            + hashlib.sha256(
                finalization_id.encode()
            ).hexdigest()
        )

    def get_by_digest(
        self,
        bundle_digest: str,
    ) -> StoredDurableMerkleBundle | None:
        key = self._bundle_key(
            bundle_digest
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableSessionMerkleProofBundle,
        ):
            raise DurableMerkleBundleCorruption(
                "Merkle bundle record has invalid value type"
            )
        bundle = record.value
        if bundle.digest != bundle_digest:
            raise DurableMerkleBundleCorruption(
                "content-addressed Merkle bundle digest mismatch"
            )
        return StoredDurableMerkleBundle(
            record.revision,
            bundle,
        )

    def index(
        self,
        finalization_id: str,
    ) -> (
        StoredDurableMerkleBundleIndex
        | None
    ):
        key = self._finalization_key(
            finalization_id
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableMerkleBundleIndex,
        ):
            raise DurableMerkleBundleCorruption(
                "Merkle finalization index has invalid value type"
            )
        if (
            record.value.finalization_id
            != finalization_id
        ):
            raise DurableMerkleBundleCorruption(
                "Merkle finalization index identity mismatch"
            )
        return StoredDurableMerkleBundleIndex(
            record.revision,
            record.value,
        )

    def get_by_finalization(
        self,
        finalization_id: str,
    ) -> StoredDurableMerkleBundle | None:
        indexed = self.index(
            finalization_id
        )
        if indexed is None:
            return None
        stored = self.get_by_digest(
            indexed.index.bundle_digest
        )
        if stored is None:
            raise DurableMerkleBundleCorruption(
                "Merkle finalization index references missing bundle"
            )
        bundle = stored.bundle
        expected = indexed.index
        if (
            bundle.finalization_id
            != expected.finalization_id
            or bundle.session_id
            != expected.session_id
            or bundle.recovery_checkpoint_digest
            != expected.recovery_checkpoint_digest
            or bundle.session_integrity_digest
            != expected.session_integrity_digest
            or bundle.journal_checkpoint.digest
            != expected.journal_checkpoint_digest
            or (
                ""
                if bundle.receipt_checkpoint
                is None
                else bundle.receipt_checkpoint.digest
            )
            != expected.receipt_checkpoint_digest
        ):
            raise DurableMerkleBundleCorruption(
                "Merkle finalization index metadata differs from bundle"
            )
        return stored

    def _put_bundle(
        self,
        bundle: DurableSessionMerkleProofBundle,
    ) -> tuple[
        StoredDurableMerkleBundle,
        bool,
    ]:
        key = self._bundle_key(
            bundle.digest
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                DurableSessionMerkleProofBundle,
            ):
                raise DurableMerkleBundleCorruption(
                    "Merkle bundle key has invalid value type"
                )
            if existing.value != bundle:
                raise DurableMerkleBundleCorruption(
                    "content-addressed Merkle bundle collision"
                )
            return (
                StoredDurableMerkleBundle(
                    existing.revision,
                    existing.value,
                ),
                False,
            )

        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                bundle,
            )
            return (
                StoredDurableMerkleBundle(
                    record.revision,
                    bundle,
                ),
                True,
            )
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if winner is None:
                raise
            if not isinstance(
                winner.value,
                DurableSessionMerkleProofBundle,
            ):
                raise DurableMerkleBundleCorruption(
                    "concurrent Merkle bundle winner has invalid type"
                )
            if winner.value != bundle:
                raise DurableMerkleBundleCorruption(
                    "concurrent content-addressed Merkle bundle differs"
                )
            return (
                StoredDurableMerkleBundle(
                    winner.revision,
                    winner.value,
                ),
                False,
            )

    def _put_index(
        self,
        bundle: DurableSessionMerkleProofBundle,
    ) -> tuple[
        StoredDurableMerkleBundleIndex,
        bool,
    ]:
        index = DurableMerkleBundleIndex.from_bundle(
            bundle
        )
        key = self._finalization_key(
            bundle.finalization_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                DurableMerkleBundleIndex,
            ):
                raise DurableMerkleBundleCorruption(
                    "Merkle finalization index key has invalid type"
                )
            if existing.value != index:
                raise DurableMerkleBundleConflict(
                    "finalization already binds different Merkle proof bundle"
                )
            return (
                StoredDurableMerkleBundleIndex(
                    existing.revision,
                    existing.value,
                ),
                False,
            )

        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                index,
            )
            return (
                StoredDurableMerkleBundleIndex(
                    record.revision,
                    index,
                ),
                True,
            )
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if winner is None:
                raise
            if not isinstance(
                winner.value,
                DurableMerkleBundleIndex,
            ):
                raise DurableMerkleBundleCorruption(
                    "concurrent Merkle index winner has invalid type"
                )
            if winner.value != index:
                raise DurableMerkleBundleConflict(
                    "concurrent finalization index binds different Merkle bundle"
                )
            return (
                StoredDurableMerkleBundleIndex(
                    winner.revision,
                    winner.value,
                ),
                False,
            )

    def put_once(
        self,
        bundle: DurableSessionMerkleProofBundle,
    ) -> DurableMerkleBundleCommit:
        if not isinstance(
            bundle,
            DurableSessionMerkleProofBundle,
        ):
            raise TypeError(
                "bundle must be DurableSessionMerkleProofBundle"
            )

        existing_index = self.index(
            bundle.finalization_id
        )
        if (
            existing_index is not None
            and existing_index.index.bundle_digest
            != bundle.digest
        ):
            raise DurableMerkleBundleConflict(
                "finalization already binds different Merkle proof bundle"
            )

        stored, bundle_created = (
            self._put_bundle(
                bundle
            )
        )
        indexed, index_created = (
            self._put_index(
                bundle
            )
        )
        return DurableMerkleBundleCommit(
            stored,
            indexed,
            bundle_created,
            index_created,
        )

    def repair_index(
        self,
        bundle_digest: str,
    ) -> StoredDurableMerkleBundleIndex:
        stored = self.get_by_digest(
            bundle_digest
        )
        if stored is None:
            raise DurableMerkleBundleStoreError(
                "cannot repair index for missing Merkle bundle"
            )
        indexed, _ = self._put_index(
            stored.bundle
        )
        return indexed

    def require_finalization(
        self,
        finalization_id: str,
        *,
        bundle_digest: str = "",
    ) -> StoredDurableMerkleBundle:
        stored = self.get_by_finalization(
            finalization_id
        )
        if stored is None:
            raise DurableMerkleBundleStoreError(
                "Merkle proof bundle is missing for finalization"
            )
        if bundle_digest:
            bundle_digest = _digest(
                "bundle_digest",
                bundle_digest,
            )
            if (
                stored.bundle.digest
                != bundle_digest
            ):
                raise DurableMerkleBundleConflict(
                    "Merkle proof bundle digest differs from expected"
                )
        return stored

    def verify_index(
        self,
        finalization_id: str,
    ) -> bool:
        try:
            stored = self.get_by_finalization(
                finalization_id
            )
        except (
            DurableMerkleBundleStoreError,
            ValueError,
        ):
            return False
        return stored is not None
