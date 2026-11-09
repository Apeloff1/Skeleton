"""Signed archival manifests for checkpointed durable evidence prefixes.

An archive manifest describes exactly which committed nodes belong to a signed
checkpointed prefix.  It is a handoff/proof artifact only: producing or signing
a manifest does not copy bytes and never authorizes local evidence deletion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpointStore,
    DurableCheckpointError,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)


def _digest(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class DurableArchiveEntry:
    sequence: int
    previous_hash: str
    node_hash: str
    kind: str
    object_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError(
                "archive entry sequence must be positive"
            )
        object.__setattr__(
            self,
            "previous_hash",
            _digest("previous_hash", self.previous_hash),
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest("node_hash", self.node_hash),
        )
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid archive entry kind")
        object.__setattr__(
            self,
            "object_digest",
            _digest(
                "object_digest",
                self.object_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "node_hash": self.node_hash,
            "kind": self.kind,
            "object_digest": self.object_digest,
        }


@dataclass(frozen=True)
class DurableArchiveManifest:
    schema_version: int
    archive_id: str
    chain_id: str
    checkpoint_digest: str
    checkpoint_sequence: int
    checkpoint_root: str
    node_count: int
    entries_digest: str
    entries: tuple[DurableArchiveEntry, ...]
    created_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable archive manifest schema"
            )
        if not self.archive_id or len(self.archive_id) > 256:
            raise ValueError("invalid archive_id")
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid chain_id")
        object.__setattr__(
            self,
            "checkpoint_digest",
            _digest(
                "checkpoint_digest",
                self.checkpoint_digest,
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_root",
            _digest(
                "checkpoint_root",
                self.checkpoint_root,
            ),
        )
        object.__setattr__(
            self,
            "entries_digest",
            _digest(
                "entries_digest",
                self.entries_digest,
            ),
        )
        for name in (
            "checkpoint_sequence",
            "node_count",
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
        entries = tuple(self.entries)
        object.__setattr__(
            self,
            "entries",
            entries,
        )
        if len(entries) != self.node_count:
            raise ValueError(
                "archive node_count differs from entries"
            )
        if self.node_count != self.checkpoint_sequence:
            raise ValueError(
                "archive prefix count differs from checkpoint sequence"
            )
        if entries:
            expected = 1
            previous = "0" * 64
            for entry in entries:
                if entry.sequence != expected:
                    raise ValueError(
                        "archive entry sequence is not contiguous"
                    )
                if entry.previous_hash != previous:
                    raise ValueError(
                        "archive entry previous hash is not contiguous"
                    )
                previous = entry.node_hash
                expected += 1
            if previous != self.checkpoint_root:
                raise ValueError(
                    "archive entries do not terminate at checkpoint root"
                )
        elif self.checkpoint_root != "0" * 64:
            raise ValueError(
                "empty archive must terminate at genesis root"
            )
        expected_entries_digest = self.compute_entries_digest(
            entries
        )
        if expected_entries_digest != self.entries_digest:
            raise ValueError(
                "archive entries_digest differs from entries"
            )
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(float(self.created_at))
            or float(self.created_at) < 0.0
        ):
            raise ValueError(
                "archive created_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "created_at",
            float(self.created_at),
        )

    @staticmethod
    def compute_entries_digest(
        entries: tuple[DurableArchiveEntry, ...],
    ) -> str:
        raw = json.dumps(
            [
                item.to_dict()
                for item in entries
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def derive_archive_id(
        chain_id: str,
        checkpoint_digest: str,
    ) -> str:
        if not chain_id:
            raise ValueError("chain_id is required")
        checkpoint_digest = _digest(
            "checkpoint_digest",
            checkpoint_digest,
        )
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "checkpoint_digest": checkpoint_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_entries: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "checkpoint_digest": self.checkpoint_digest,
            "checkpoint_sequence": self.checkpoint_sequence,
            "checkpoint_root": self.checkpoint_root,
            "node_count": self.node_count,
            "entries_digest": self.entries_digest,
            "created_at": self.created_at,
        }
        if include_entries:
            data["entries"] = [
                item.to_dict()
                for item in self.entries
            ]
        return data

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_entries=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedDurableArchiveManifest:
    manifest: DurableArchiveManifest
    signature: SignedArtifact

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "manifest_digest": self.manifest.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableArchiveVerification:
    valid: bool
    archive_id: str
    chain_id: str
    checkpoint_digest: str
    checkpoint_sequence: int
    checkpoint_root: str
    node_count: int
    current_sequence: int
    current_root: str
    checkpoint_valid: bool
    prefix_valid: bool
    committed_ancestor: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        if not self.archive_id or len(self.archive_id) > 256:
            raise ValueError("invalid archive_id")
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid chain_id")
        object.__setattr__(
            self,
            "checkpoint_digest",
            _digest(
                "checkpoint_digest",
                self.checkpoint_digest,
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_root",
            _digest(
                "checkpoint_root",
                self.checkpoint_root,
            ),
        )
        object.__setattr__(
            self,
            "current_root",
            _digest(
                "current_root",
                self.current_root,
            ),
        )
        for name in (
            "checkpoint_sequence",
            "node_count",
            "current_sequence",
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
            "checkpoint_valid",
            "prefix_valid",
            "committed_ancestor",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "archive_id": self.archive_id,
            "chain_id": self.chain_id,
            "checkpoint_digest": self.checkpoint_digest,
            "checkpoint_sequence": self.checkpoint_sequence,
            "checkpoint_root": self.checkpoint_root,
            "node_count": self.node_count,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "checkpoint_valid": self.checkpoint_valid,
            "prefix_valid": self.prefix_valid,
            "committed_ancestor": self.committed_ancestor,
            "reasons": list(self.reasons),
        }


class DurableArchiveError(RuntimeError):
    pass


class DurableArchiveManifestBuilder:
    """Build and verify signed checkpoint-prefix manifests."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        signer: ArtifactSigner,
        *,
        clock: Callable[[], float] = time.time,
        max_entries: int = 100_000,
    ) -> None:
        if not isinstance(
            checkpoints,
            DurableChainCheckpointStore,
        ):
            raise TypeError(
                "checkpoints must be DurableChainCheckpointStore"
            )
        if not isinstance(signer, ArtifactSigner):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or max_entries <= 0
        ):
            raise ValueError(
                "max_entries must be positive integer"
            )
        self.checkpoints = checkpoints
        self.signer = signer
        self._clock = clock
        self.max_entries = max_entries

    @staticmethod
    def _entry(item) -> DurableArchiveEntry:
        if hasattr(item, "event_hash"):
            kind = str(item.kind)
            node_hash = str(item.event_hash)
            object_digest = str(item.event_hash)
        elif hasattr(item, "receipt_hash"):
            kind = "execution.receipt"
            node_hash = str(item.receipt_hash)
            object_digest = str(
                item.receipt.fingerprint
            )
        elif hasattr(item, "node_hash"):
            kind = str(
                getattr(item, "kind", "evidence.node")
            )
            node_hash = str(item.node_hash)
            object_digest = str(item.node_hash)
        else:
            raise DurableArchiveError(
                "unsupported durable archive node type"
            )
        return DurableArchiveEntry(
            int(item.sequence),
            str(item.previous_hash),
            node_hash,
            kind,
            object_digest,
        )

    def build(
        self,
        checkpoint: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> SignedDurableArchiveManifest:
        if not isinstance(
            checkpoint,
            SignedDurableChainCheckpoint,
        ):
            raise TypeError(
                "checkpoint must be SignedDurableChainCheckpoint"
            )
        try:
            verification = self.checkpoints.require(
                checkpoint,
                chain,
            )
        except DurableCheckpointError as exc:
            raise DurableArchiveError(
                f"checkpoint failed canonical verification: {exc}"
            ) from exc
        if not verification.valid:
            raise DurableArchiveError(
                "checkpoint failed verification"
            )
        prefix = chain.snapshot_at(
            checkpoint.checkpoint.root_hash
        )
        if len(prefix) > self.max_entries:
            raise DurableArchiveError(
                "archive entry bound exceeded"
            )
        entries = tuple(
            self._entry(item)
            for item in prefix
        )
        archive_id = DurableArchiveManifest.derive_archive_id(
            checkpoint.checkpoint.chain_id,
            checkpoint.checkpoint.digest,
        )
        created_at = self._clock()
        manifest = DurableArchiveManifest(
            1,
            archive_id,
            checkpoint.checkpoint.chain_id,
            checkpoint.checkpoint.digest,
            checkpoint.checkpoint.sequence,
            checkpoint.checkpoint.root_hash,
            len(entries),
            DurableArchiveManifest.compute_entries_digest(
                entries
            ),
            entries,
            created_at,
        )
        signature = self.signer.sign(
            "durable-archive-manifest",
            manifest.digest,
            metadata={
                "archive_id": archive_id,
                "chain_id": manifest.chain_id,
                "checkpoint_digest": (
                    manifest.checkpoint_digest
                ),
            },
        )
        return SignedDurableArchiveManifest(
            manifest,
            signature,
        )

    def inspect(
        self,
        item: SignedDurableArchiveManifest,
        checkpoint: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> DurableArchiveVerification:
        if not isinstance(
            item,
            SignedDurableArchiveManifest,
        ):
            raise TypeError(
                "item must be SignedDurableArchiveManifest"
            )
        if not isinstance(
            checkpoint,
            SignedDurableChainCheckpoint,
        ):
            raise TypeError(
                "checkpoint must be SignedDurableChainCheckpoint"
            )
        reasons: list[str] = []

        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError:
            reasons.append(
                "archive manifest signature is invalid"
            )
        if (
            item.signature.artifact_type
            != "durable-archive-manifest"
        ):
            reasons.append(
                "archive manifest artifact type is invalid"
            )
        if (
            item.signature.artifact_digest
            != item.manifest.digest
        ):
            reasons.append(
                "archive manifest signature digest differs from manifest"
            )

        manifest = item.manifest
        if (
            manifest.chain_id
            != checkpoint.checkpoint.chain_id
        ):
            reasons.append(
                "archive chain_id differs from checkpoint"
            )
        if (
            manifest.checkpoint_digest
            != checkpoint.checkpoint.digest
        ):
            reasons.append(
                "archive checkpoint digest differs from checkpoint"
            )
        if (
            manifest.checkpoint_sequence
            != checkpoint.checkpoint.sequence
        ):
            reasons.append(
                "archive checkpoint sequence differs from checkpoint"
            )
        if (
            manifest.checkpoint_root
            != checkpoint.checkpoint.root_hash
        ):
            reasons.append(
                "archive checkpoint root differs from checkpoint"
            )

        checkpoint_report = self.checkpoints.inspect(
            checkpoint,
            chain,
        )
        checkpoint_valid = checkpoint_report.valid

        try:
            prefix = chain.snapshot_at(
                manifest.checkpoint_root
            )
            entries = tuple(
                self._entry(node)
                for node in prefix
            )
            prefix_valid = (
                entries == manifest.entries
                and DurableArchiveManifest.compute_entries_digest(
                    entries
                )
                == manifest.entries_digest
                and len(entries) == manifest.node_count
            )
        except Exception as exc:
            prefix = ()
            prefix_valid = False
            reasons.append(
                "archive prefix reconstruction failed: "
                f"{type(exc).__name__}"
            )

        if not checkpoint_valid:
            reasons.append(
                "archive checkpoint failed canonical verification"
            )
        if not prefix_valid:
            reasons.append(
                "archive manifest entries differ from committed prefix"
            )

        try:
            ancestor = chain.root_is_ancestor(
                manifest.checkpoint_root
            )
            head = chain.head()
            current_sequence = int(
                head.sequence
            )
            current_root = str(
                head.root_hash
            )
        except Exception as exc:
            ancestor = False
            current_sequence = 0
            current_root = "0" * 64
            reasons.append(
                "archive current-chain inspection failed: "
                f"{type(exc).__name__}"
            )

        if not ancestor:
            reasons.append(
                "archive checkpoint root is not a committed ancestor"
            )

        return DurableArchiveVerification(
            not reasons,
            manifest.archive_id,
            manifest.chain_id,
            manifest.checkpoint_digest,
            manifest.checkpoint_sequence,
            manifest.checkpoint_root,
            manifest.node_count,
            current_sequence,
            current_root,
            checkpoint_valid,
            prefix_valid,
            ancestor,
            tuple(reasons),
        )

    def require(
        self,
        item: SignedDurableArchiveManifest,
        checkpoint: SignedDurableChainCheckpoint,
        chain: CheckpointableEvidenceChain,
    ) -> DurableArchiveVerification:
        report = self.inspect(
            item,
            checkpoint,
            chain,
        )
        if not report.valid:
            raise DurableArchiveError(
                "; ".join(report.reasons)
            )
        return report
