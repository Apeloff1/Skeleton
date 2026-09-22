"""Signed Merkle checkpoints and compact inclusion proofs for durable chains.

The journal and receipt hash chains remain authoritative.  This module adds a
second, proof-oriented commitment over an already verified chain prefix.  The
Merkle checkpoint is signed only after native chain continuity and historical
root ancestry are verified.

A proof never authorizes execution and never replaces the underlying durable
chain.  Its purpose is bounded verification of inclusion in very large retained
histories, including after the live head has advanced.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable, Protocol, Sequence

from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)


MERKLE_ALGORITHM = "sha256-domain-separated-merkle-v1"
MERKLE_CHECKPOINT_ARTIFACT = "shell-ai-durable-merkle-checkpoint-v1"
LEAF_DOMAIN = b"shell-ai-durable-merkle-leaf-v1\x00"
NODE_DOMAIN = b"shell-ai-durable-merkle-node-v1\x00"
EMPTY_DOMAIN = b"shell-ai-durable-merkle-empty-v1\x00"


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
    *,
    maximum: int = 256,
) -> str:
    if not value or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _sequence(name: str, value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{name} must be positive integer"
        )
    return value


def _canonical_digest(
    value: object,
) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableMerkleChainKind(str, Enum):
    JOURNAL = "journal"
    RECEIPTS = "receipts"


class DurableMerkleSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class MerkleCheckpointChain(Protocol):
    def snapshot(self): ...

    def snapshot_at(self, root_hash: str): ...

    def verify(self) -> bool: ...

    def verify_root(self, root_hash: str) -> bool: ...

    def root_is_ancestor(self, root_hash: str) -> bool: ...

    def root_hash(self) -> str: ...


@dataclass(frozen=True)
class DurableMerkleLeaf:
    chain_id: str
    chain_kind: DurableMerkleChainKind
    sequence: int
    item_hash: str
    previous_hash: str
    subject_id: str
    payload_fingerprint: str
    leaf_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "chain_kind",
            DurableMerkleChainKind(
                self.chain_kind
            ),
        )
        object.__setattr__(
            self,
            "sequence",
            _sequence(
                "sequence",
                self.sequence,
            ),
        )
        for name in (
            "item_hash",
            "previous_hash",
            "payload_fingerprint",
            "leaf_hash",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        object.__setattr__(
            self,
            "subject_id",
            _identity(
                "subject_id",
                self.subject_id,
                maximum=256,
            ),
        )
        expected = self.compute_hash(
            chain_id=self.chain_id,
            chain_kind=self.chain_kind,
            sequence=self.sequence,
            item_hash=self.item_hash,
            previous_hash=self.previous_hash,
            subject_id=self.subject_id,
            payload_fingerprint=(
                self.payload_fingerprint
            ),
        )
        if self.leaf_hash != expected:
            raise ValueError(
                "Merkle leaf hash does not match leaf content"
            )

    @staticmethod
    def compute_hash(
        *,
        chain_id: str,
        chain_kind: DurableMerkleChainKind,
        sequence: int,
        item_hash: str,
        previous_hash: str,
        subject_id: str,
        payload_fingerprint: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=160,
        )
        chain_kind = DurableMerkleChainKind(
            chain_kind
        )
        sequence = _sequence(
            "sequence",
            sequence,
        )
        item_hash = _digest(
            "item_hash",
            item_hash,
        )
        previous_hash = _digest(
            "previous_hash",
            previous_hash,
        )
        subject_id = _identity(
            "subject_id",
            subject_id,
            maximum=256,
        )
        payload_fingerprint = _digest(
            "payload_fingerprint",
            payload_fingerprint,
        )
        payload = json.dumps(
            {
                "chain_id": chain_id,
                "chain_kind": chain_kind.value,
                "sequence": sequence,
                "item_hash": item_hash,
                "previous_hash": previous_hash,
                "subject_id": subject_id,
                "payload_fingerprint": (
                    payload_fingerprint
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(
            LEAF_DOMAIN + payload
        ).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        chain_id: str,
        chain_kind: DurableMerkleChainKind,
        sequence: int,
        item_hash: str,
        previous_hash: str,
        subject_id: str,
        payload_fingerprint: str,
    ) -> "DurableMerkleLeaf":
        leaf_hash = cls.compute_hash(
            chain_id=chain_id,
            chain_kind=chain_kind,
            sequence=sequence,
            item_hash=item_hash,
            previous_hash=previous_hash,
            subject_id=subject_id,
            payload_fingerprint=(
                payload_fingerprint
            ),
        )
        return cls(
            chain_id,
            chain_kind,
            sequence,
            item_hash,
            previous_hash,
            subject_id,
            payload_fingerprint,
            leaf_hash,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "chain_kind": self.chain_kind.value,
            "sequence": self.sequence,
            "item_hash": self.item_hash,
            "previous_hash": self.previous_hash,
            "subject_id": self.subject_id,
            "payload_fingerprint": (
                self.payload_fingerprint
            ),
            "leaf_hash": self.leaf_hash,
        }


@dataclass(frozen=True)
class DurableMerkleProofStep:
    sibling_hash: str
    sibling_side: DurableMerkleSide
    duplicated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sibling_hash",
            _digest(
                "sibling_hash",
                self.sibling_hash,
            ),
        )
        object.__setattr__(
            self,
            "sibling_side",
            DurableMerkleSide(
                self.sibling_side
            ),
        )
        if not isinstance(
            self.duplicated,
            bool,
        ):
            raise ValueError(
                "duplicated must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "sibling_hash": self.sibling_hash,
            "sibling_side": (
                self.sibling_side.value
            ),
            "duplicated": self.duplicated,
        }


@dataclass(frozen=True)
class DurableMerkleCheckpoint:
    schema_version: int
    chain_id: str
    chain_kind: DurableMerkleChainKind
    chain_root: str
    sequence_count: int
    merkle_root: str
    leaves_digest: str
    algorithm: str = MERKLE_ALGORITHM

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported Merkle checkpoint schema"
            )
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "chain_kind",
            DurableMerkleChainKind(
                self.chain_kind
            ),
        )
        object.__setattr__(
            self,
            "chain_root",
            _digest(
                "chain_root",
                self.chain_root,
            ),
        )
        object.__setattr__(
            self,
            "merkle_root",
            _digest(
                "merkle_root",
                self.merkle_root,
            ),
        )
        object.__setattr__(
            self,
            "leaves_digest",
            _digest(
                "leaves_digest",
                self.leaves_digest,
            ),
        )
        if (
            isinstance(self.sequence_count, bool)
            or not isinstance(
                self.sequence_count,
                int,
            )
            or self.sequence_count <= 0
        ):
            raise ValueError(
                "sequence_count must be positive integer"
            )
        if self.algorithm != MERKLE_ALGORITHM:
            raise ValueError(
                "unsupported Merkle algorithm"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "chain_kind": self.chain_kind.value,
            "chain_root": self.chain_root,
            "sequence_count": self.sequence_count,
            "merkle_root": self.merkle_root,
            "leaves_digest": self.leaves_digest,
            "algorithm": self.algorithm,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableMerkleCheckpoint:
    checkpoint: DurableMerkleCheckpoint
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.checkpoint,
            DurableMerkleCheckpoint,
        ):
            raise TypeError(
                "checkpoint must be DurableMerkleCheckpoint"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != MERKLE_CHECKPOINT_ARTIFACT
        ):
            raise ValueError(
                "Merkle checkpoint signature artifact type mismatch"
            )
        if (
            self.signature.artifact_digest
            != self.checkpoint.digest
        ):
            raise ValueError(
                "Merkle checkpoint signature digest mismatch"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "checkpoint": (
                self.checkpoint.to_dict()
            ),
            "signature": (
                self.signature.to_dict()
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableMerkleProof:
    schema_version: int
    checkpoint_digest: str
    chain_id: str
    chain_kind: DurableMerkleChainKind
    sequence: int
    leaf_index: int
    tree_size: int
    leaf: DurableMerkleLeaf
    siblings: tuple[
        DurableMerkleProofStep,
        ...,
    ]
    algorithm: str = MERKLE_ALGORITHM

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported Merkle proof schema"
            )
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
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "chain_kind",
            DurableMerkleChainKind(
                self.chain_kind
            ),
        )
        object.__setattr__(
            self,
            "sequence",
            _sequence(
                "sequence",
                self.sequence,
            ),
        )
        if (
            isinstance(self.leaf_index, bool)
            or not isinstance(
                self.leaf_index,
                int,
            )
            or self.leaf_index < 0
        ):
            raise ValueError(
                "leaf_index must be non-negative integer"
            )
        if (
            isinstance(self.tree_size, bool)
            or not isinstance(
                self.tree_size,
                int,
            )
            or self.tree_size <= 0
        ):
            raise ValueError(
                "tree_size must be positive integer"
            )
        if self.leaf_index >= self.tree_size:
            raise ValueError(
                "leaf_index outside Merkle tree"
            )
        if not isinstance(
            self.leaf,
            DurableMerkleLeaf,
        ):
            raise TypeError(
                "leaf must be DurableMerkleLeaf"
            )
        if self.leaf.sequence != self.sequence:
            raise ValueError(
                "Merkle proof sequence/leaf mismatch"
            )
        if self.leaf.chain_id != self.chain_id:
            raise ValueError(
                "Merkle proof chain_id/leaf mismatch"
            )
        if (
            self.leaf.chain_kind
            is not self.chain_kind
        ):
            raise ValueError(
                "Merkle proof chain kind/leaf mismatch"
            )
        object.__setattr__(
            self,
            "siblings",
            tuple(self.siblings),
        )
        if not all(
            isinstance(
                step,
                DurableMerkleProofStep,
            )
            for step in self.siblings
        ):
            raise TypeError(
                "siblings must contain Merkle proof steps"
            )
        if self.algorithm != MERKLE_ALGORITHM:
            raise ValueError(
                "unsupported Merkle algorithm"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "checkpoint_digest": (
                self.checkpoint_digest
            ),
            "chain_id": self.chain_id,
            "chain_kind": self.chain_kind.value,
            "sequence": self.sequence,
            "leaf_index": self.leaf_index,
            "tree_size": self.tree_size,
            "leaf": self.leaf.to_dict(),
            "siblings": [
                step.to_dict()
                for step in self.siblings
            ],
            "algorithm": self.algorithm,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableMerkleVerification:
    ok: bool
    checkpoint_signature_valid: bool
    checkpoint_matches_chain: bool
    proof_valid: bool
    subject_matches: bool
    payload_matches: bool
    reconstructed_root: str
    issues: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "ok",
            "checkpoint_signature_valid",
            "checkpoint_matches_chain",
            "proof_valid",
            "subject_matches",
            "payload_matches",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "reconstructed_root",
            _digest(
                "reconstructed_root",
                self.reconstructed_root,
            ),
        )
        object.__setattr__(
            self,
            "issues",
            tuple(self.issues),
        )
        if any(
            not issue
            or len(issue) > 2048
            for issue in self.issues
        ):
            raise ValueError(
                "invalid Merkle verification issue"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checkpoint_signature_valid": (
                self.checkpoint_signature_valid
            ),
            "checkpoint_matches_chain": (
                self.checkpoint_matches_chain
            ),
            "proof_valid": self.proof_valid,
            "subject_matches": (
                self.subject_matches
            ),
            "payload_matches": (
                self.payload_matches
            ),
            "reconstructed_root": (
                self.reconstructed_root
            ),
            "issues": list(self.issues),
        }


class DurableMerkleError(RuntimeError):
    pass


class DurableMerkleAuthority:
    """Build and verify signed Merkle commitments for durable chain prefixes."""

    def __init__(
        self,
        signer: ArtifactSigner,
        *,
        max_leaves: int = 1_000_000,
    ) -> None:
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if (
            isinstance(max_leaves, bool)
            or not isinstance(
                max_leaves,
                int,
            )
            or max_leaves <= 0
        ):
            raise ValueError(
                "max_leaves must be positive integer"
            )
        self.signer = signer
        self.max_leaves = max_leaves

    @staticmethod
    def _item_sequence(
        item: object,
    ) -> int:
        value = getattr(
            item,
            "sequence",
            None,
        )
        return _sequence(
            "item sequence",
            value,
        )

    @staticmethod
    def _item_previous_hash(
        item: object,
    ) -> str:
        value = getattr(
            item,
            "previous_hash",
            None,
        )
        if not isinstance(value, str):
            raise DurableMerkleError(
                "chain item does not expose previous_hash"
            )
        return _digest(
            "previous_hash",
            value,
        )

    @staticmethod
    def _item_hash(
        item: object,
        kind: DurableMerkleChainKind,
    ) -> str:
        attribute = (
            "event_hash"
            if kind is DurableMerkleChainKind.JOURNAL
            else "receipt_hash"
        )
        value = getattr(
            item,
            attribute,
            None,
        )
        if not isinstance(value, str):
            raise DurableMerkleError(
                f"chain item does not expose {attribute}"
            )
        return _digest(
            attribute,
            value,
        )

    @staticmethod
    def _subject(
        item: object,
        kind: DurableMerkleChainKind,
    ) -> tuple[str, str]:
        if kind is DurableMerkleChainKind.JOURNAL:
            event_hash = getattr(
                item,
                "event_hash",
                None,
            )
            if not isinstance(
                event_hash,
                str,
            ):
                raise DurableMerkleError(
                    "journal item missing event_hash"
                )
            digest = _digest(
                "event_hash",
                event_hash,
            )
            return digest, digest

        receipt = getattr(
            item,
            "receipt",
            None,
        )
        if receipt is None:
            raise DurableMerkleError(
                "receipt item missing receipt payload"
            )
        receipt_id = getattr(
            receipt,
            "receipt_id",
            None,
        )
        fingerprint = getattr(
            receipt,
            "fingerprint",
            None,
        )
        if not isinstance(
            receipt_id,
            str,
        ):
            raise DurableMerkleError(
                "receipt payload missing receipt_id"
            )
        if not isinstance(
            fingerprint,
            str,
        ):
            raise DurableMerkleError(
                "receipt payload missing fingerprint"
            )
        return (
            _identity(
                "receipt_id",
                receipt_id,
                maximum=256,
            ),
            _digest(
                "receipt fingerprint",
                fingerprint,
            ),
        )

    @classmethod
    def leaf_from_item(
        cls,
        *,
        chain_id: str,
        chain_kind: DurableMerkleChainKind,
        item: object,
    ) -> DurableMerkleLeaf:
        chain_kind = DurableMerkleChainKind(
            chain_kind
        )
        subject_id, payload_fingerprint = (
            cls._subject(
                item,
                chain_kind,
            )
        )
        return DurableMerkleLeaf.create(
            chain_id=chain_id,
            chain_kind=chain_kind,
            sequence=cls._item_sequence(
                item
            ),
            item_hash=cls._item_hash(
                item,
                chain_kind,
            ),
            previous_hash=(
                cls._item_previous_hash(
                    item
                )
            ),
            subject_id=subject_id,
            payload_fingerprint=(
                payload_fingerprint
            ),
        )

    @staticmethod
    def empty_root() -> str:
        return hashlib.sha256(
            EMPTY_DOMAIN
        ).hexdigest()

    @staticmethod
    def node_hash(
        left_hash: str,
        right_hash: str,
    ) -> str:
        left_hash = _digest(
            "left_hash",
            left_hash,
        )
        right_hash = _digest(
            "right_hash",
            right_hash,
        )
        return hashlib.sha256(
            NODE_DOMAIN
            + bytes.fromhex(left_hash)
            + bytes.fromhex(right_hash)
        ).hexdigest()

    @classmethod
    def merkle_root(
        cls,
        leaves: Sequence[
            DurableMerkleLeaf
        ],
    ) -> str:
        if not leaves:
            return cls.empty_root()
        level = [
            leaf.leaf_hash
            for leaf in leaves
        ]
        while len(level) > 1:
            next_level: list[str] = []
            for index in range(
                0,
                len(level),
                2,
            ):
                left = level[index]
                right = (
                    level[index + 1]
                    if index + 1 < len(level)
                    else left
                )
                next_level.append(
                    cls.node_hash(
                        left,
                        right,
                    )
                )
            level = next_level
        return level[0]

    @staticmethod
    def leaves_digest(
        leaves: Sequence[
            DurableMerkleLeaf
        ],
    ) -> str:
        return _canonical_digest(
            [
                leaf.to_dict()
                for leaf in leaves
            ]
        )

    @classmethod
    def _validate_continuity(
        cls,
        leaves: Sequence[
            DurableMerkleLeaf
        ],
        *,
        expected_chain_root: str,
    ) -> None:
        if not leaves:
            raise DurableMerkleError(
                "Merkle checkpoint requires non-empty chain prefix"
            )
        expected_sequence = 1
        previous = leaves[0].previous_hash
        for index, leaf in enumerate(
            leaves,
        ):
            if leaf.sequence != expected_sequence:
                raise DurableMerkleError(
                    "Merkle prefix sequence is not contiguous from one"
                )
            if index > 0 and (
                leaf.previous_hash
                != leaves[index - 1].item_hash
            ):
                raise DurableMerkleError(
                    "Merkle prefix native chain continuity failed"
                )
            expected_sequence += 1
            previous = leaf.item_hash
        if previous != expected_chain_root:
            raise DurableMerkleError(
                "Merkle prefix terminal item does not match chain root"
            )

    def _snapshot(
        self,
        chain: MerkleCheckpointChain,
        root_hash: str,
    ) -> tuple[object, ...]:
        if not root_hash:
            if not chain.verify():
                raise DurableMerkleError(
                    "durable chain failed integrity verification"
                )
            items = tuple(
                chain.snapshot()
            )
        else:
            root_hash = _digest(
                "root_hash",
                root_hash,
            )
            if not chain.verify_root(
                root_hash
            ):
                raise DurableMerkleError(
                    "historical durable chain root failed verification"
                )
            if not chain.root_is_ancestor(
                root_hash
            ):
                raise DurableMerkleError(
                    "historical durable chain root is not committed ancestor"
                )
            items = tuple(
                chain.snapshot_at(
                    root_hash
                )
            )
        if not items:
            raise DurableMerkleError(
                "cannot checkpoint an empty durable chain"
            )
        if len(items) > self.max_leaves:
            raise DurableMerkleError(
                "Merkle checkpoint leaf bound exceeded"
            )
        return items

    def build(
        self,
        chain: MerkleCheckpointChain,
        *,
        chain_id: str,
        chain_kind: DurableMerkleChainKind,
        root_hash: str = "",
    ) -> tuple[
        SignedDurableMerkleCheckpoint,
        tuple[DurableMerkleLeaf, ...],
    ]:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=160,
        )
        chain_kind = DurableMerkleChainKind(
            chain_kind
        )
        items = self._snapshot(
            chain,
            root_hash,
        )
        leaves = tuple(
            self.leaf_from_item(
                chain_id=chain_id,
                chain_kind=chain_kind,
                item=item,
            )
            for item in items
        )
        chain_root = leaves[-1].item_hash
        self._validate_continuity(
            leaves,
            expected_chain_root=(
                chain_root
            ),
        )
        checkpoint = DurableMerkleCheckpoint(
            1,
            chain_id,
            chain_kind,
            chain_root,
            len(leaves),
            self.merkle_root(
                leaves
            ),
            self.leaves_digest(
                leaves
            ),
        )
        signature = self.signer.sign(
            MERKLE_CHECKPOINT_ARTIFACT,
            checkpoint.digest,
            metadata={
                "chain_id": chain_id,
                "chain_kind": (
                    chain_kind.value
                ),
                "chain_root": (
                    checkpoint.chain_root
                ),
                "sequence_count": str(
                    checkpoint.sequence_count
                ),
                "algorithm": MERKLE_ALGORITHM,
            },
        )
        return (
            SignedDurableMerkleCheckpoint(
                checkpoint,
                signature,
            ),
            leaves,
        )

    @classmethod
    def _proof_steps(
        cls,
        leaves: Sequence[
            DurableMerkleLeaf
        ],
        leaf_index: int,
    ) -> tuple[
        DurableMerkleProofStep,
        ...,
    ]:
        if not leaves:
            raise DurableMerkleError(
                "cannot prove empty Merkle tree"
            )
        if (
            isinstance(leaf_index, bool)
            or not isinstance(
                leaf_index,
                int,
            )
            or not 0 <= leaf_index < len(leaves)
        ):
            raise ValueError(
                "leaf_index outside Merkle tree"
            )
        level = [
            leaf.leaf_hash
            for leaf in leaves
        ]
        index = leaf_index
        steps: list[
            DurableMerkleProofStep
        ] = []
        while len(level) > 1:
            is_right = index % 2 == 1
            if is_right:
                sibling_index = index - 1
                sibling_side = (
                    DurableMerkleSide.LEFT
                )
                duplicated = False
            else:
                sibling_index = index + 1
                if sibling_index >= len(level):
                    sibling_index = index
                    duplicated = True
                else:
                    duplicated = False
                sibling_side = (
                    DurableMerkleSide.RIGHT
                )
            steps.append(
                DurableMerkleProofStep(
                    level[sibling_index],
                    sibling_side,
                    duplicated,
                )
            )
            next_level: list[str] = []
            for cursor in range(
                0,
                len(level),
                2,
            ):
                left = level[cursor]
                right = (
                    level[cursor + 1]
                    if cursor + 1
                    < len(level)
                    else left
                )
                next_level.append(
                    cls.node_hash(
                        left,
                        right,
                    )
                )
            level = next_level
            index //= 2
        return tuple(steps)

    @classmethod
    def reconstruct_root(
        cls,
        proof: DurableMerkleProof,
    ) -> str:
        current = proof.leaf.leaf_hash
        index = proof.leaf_index
        width = proof.tree_size
        for step in proof.siblings:
            if step.duplicated:
                if (
                    step.sibling_side
                    is not DurableMerkleSide.RIGHT
                    or step.sibling_hash != current
                    or index % 2 != 0
                    or index + 1 < width
                ):
                    raise DurableMerkleError(
                        "invalid duplicated Merkle proof step"
                    )
            if (
                step.sibling_side
                is DurableMerkleSide.LEFT
            ):
                current = cls.node_hash(
                    step.sibling_hash,
                    current,
                )
            else:
                current = cls.node_hash(
                    current,
                    step.sibling_hash,
                )
            index //= 2
            width = (
                width + 1
            ) // 2
        if width != 1:
            raise DurableMerkleError(
                "Merkle proof ended before root"
            )
        return current

    def prove(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
        leaves: Sequence[
            DurableMerkleLeaf
        ],
        *,
        sequence: int,
    ) -> DurableMerkleProof:
        self.verify_checkpoint_signature(
            signed_checkpoint
        )
        checkpoint = (
            signed_checkpoint.checkpoint
        )
        sequence = _sequence(
            "sequence",
            sequence,
        )
        leaves = tuple(leaves)
        if (
            len(leaves)
            != checkpoint.sequence_count
        ):
            raise DurableMerkleError(
                "Merkle proof leaves length differs from checkpoint"
            )
        if (
            self.leaves_digest(
                leaves
            )
            != checkpoint.leaves_digest
        ):
            raise DurableMerkleError(
                "Merkle proof leaves digest differs from checkpoint"
            )
        if (
            self.merkle_root(
                leaves
            )
            != checkpoint.merkle_root
        ):
            raise DurableMerkleError(
                "Merkle proof leaves root differs from checkpoint"
            )
        index = sequence - 1
        if not 0 <= index < len(leaves):
            raise DurableMerkleError(
                "requested sequence outside checkpoint"
            )
        leaf = leaves[index]
        if leaf.sequence != sequence:
            raise DurableMerkleError(
                "Merkle leaf sequence index mismatch"
            )
        return DurableMerkleProof(
            1,
            signed_checkpoint.digest,
            checkpoint.chain_id,
            checkpoint.chain_kind,
            sequence,
            index,
            len(leaves),
            leaf,
            self._proof_steps(
                leaves,
                index,
            ),
        )

    def verify_checkpoint_signature(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
    ) -> None:
        if not isinstance(
            signed_checkpoint,
            SignedDurableMerkleCheckpoint,
        ):
            raise TypeError(
                "signed_checkpoint must be SignedDurableMerkleCheckpoint"
            )
        try:
            self.signer.verify(
                signed_checkpoint.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableMerkleError(
                "Merkle checkpoint signature verification failed"
            ) from exc
        if (
            signed_checkpoint.signature.artifact_digest
            != signed_checkpoint.checkpoint.digest
        ):
            raise DurableMerkleError(
                "Merkle checkpoint signature digest mismatch"
            )

    def verify_checkpoint_against_chain(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
        chain: MerkleCheckpointChain,
    ) -> bool:
        try:
            self.verify_checkpoint_signature(
                signed_checkpoint
            )
            checkpoint = (
                signed_checkpoint.checkpoint
            )
            items = self._snapshot(
                chain,
                checkpoint.chain_root,
            )
            if (
                len(items)
                != checkpoint.sequence_count
            ):
                return False
            leaves = tuple(
                self.leaf_from_item(
                    chain_id=(
                        checkpoint.chain_id
                    ),
                    chain_kind=(
                        checkpoint.chain_kind
                    ),
                    item=item,
                )
                for item in items
            )
            return (
                self.merkle_root(
                    leaves
                )
                == checkpoint.merkle_root
                and self.leaves_digest(
                    leaves
                )
                == checkpoint.leaves_digest
            )
        except (
            DurableMerkleError,
            ValueError,
            TypeError,
        ):
            return False

    def inspect_proof(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
        proof: DurableMerkleProof,
        *,
        expected_subject_id: str = "",
        expected_payload_fingerprint: str = "",
        chain: MerkleCheckpointChain | None = None,
    ) -> DurableMerkleVerification:
        issues: list[str] = []
        signature_valid = True
        checkpoint_matches_chain = (
            chain is None
        )
        proof_valid = True
        subject_matches = True
        payload_matches = True
        reconstructed = self.empty_root()

        try:
            self.verify_checkpoint_signature(
                signed_checkpoint
            )
        except Exception as exc:
            signature_valid = False
            issues.append(
                "checkpoint signature invalid: "
                f"{type(exc).__name__}"
            )

        checkpoint = (
            signed_checkpoint.checkpoint
        )
        if chain is not None:
            checkpoint_matches_chain = (
                self.verify_checkpoint_against_chain(
                    signed_checkpoint,
                    chain,
                )
            )
            if not checkpoint_matches_chain:
                issues.append(
                    "checkpoint does not match authoritative chain"
                )

        if (
            proof.checkpoint_digest
            != signed_checkpoint.digest
        ):
            proof_valid = False
            issues.append(
                "proof checkpoint digest mismatch"
            )
        if proof.chain_id != checkpoint.chain_id:
            proof_valid = False
            issues.append(
                "proof chain_id mismatch"
            )
        if (
            proof.chain_kind
            is not checkpoint.chain_kind
        ):
            proof_valid = False
            issues.append(
                "proof chain kind mismatch"
            )
        if (
            proof.tree_size
            != checkpoint.sequence_count
        ):
            proof_valid = False
            issues.append(
                "proof tree size mismatch"
            )

        try:
            reconstructed = (
                self.reconstruct_root(
                    proof
                )
            )
        except Exception as exc:
            proof_valid = False
            issues.append(
                "proof root reconstruction failed: "
                f"{type(exc).__name__}"
            )
        else:
            if (
                reconstructed
                != checkpoint.merkle_root
            ):
                proof_valid = False
                issues.append(
                    "proof reconstructed root mismatch"
                )

        if expected_subject_id:
            if (
                proof.leaf.subject_id
                != expected_subject_id
            ):
                subject_matches = False
                issues.append(
                    "proof subject identity mismatch"
                )
        if expected_payload_fingerprint:
            expected_payload_fingerprint = (
                _digest(
                    "expected_payload_fingerprint",
                    expected_payload_fingerprint,
                )
            )
            if (
                proof.leaf.payload_fingerprint
                != expected_payload_fingerprint
            ):
                payload_matches = False
                issues.append(
                    "proof payload fingerprint mismatch"
                )

        ok = (
            signature_valid
            and checkpoint_matches_chain
            and proof_valid
            and subject_matches
            and payload_matches
            and not issues
        )
        return DurableMerkleVerification(
            ok,
            signature_valid,
            checkpoint_matches_chain,
            proof_valid,
            subject_matches,
            payload_matches,
            reconstructed,
            tuple(issues),
        )

    def require_proof(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
        proof: DurableMerkleProof,
        *,
        expected_subject_id: str = "",
        expected_payload_fingerprint: str = "",
        chain: MerkleCheckpointChain | None = None,
    ) -> DurableMerkleVerification:
        report = self.inspect_proof(
            signed_checkpoint,
            proof,
            expected_subject_id=(
                expected_subject_id
            ),
            expected_payload_fingerprint=(
                expected_payload_fingerprint
            ),
            chain=chain,
        )
        if not report.ok:
            detail = (
                report.issues[0]
                if report.issues
                else "Merkle proof verification failed"
            )
            raise DurableMerkleError(
                detail
            )
        return report

    def proofs_for_sequences(
        self,
        signed_checkpoint: SignedDurableMerkleCheckpoint,
        leaves: Sequence[
            DurableMerkleLeaf
        ],
        sequences: Iterable[int],
    ) -> tuple[
        DurableMerkleProof,
        ...,
    ]:
        seen: set[int] = set()
        proofs: list[
            DurableMerkleProof
        ] = []
        for sequence in sequences:
            sequence = _sequence(
                "sequence",
                sequence,
            )
            if sequence in seen:
                continue
            seen.add(sequence)
            proofs.append(
                self.prove(
                    signed_checkpoint,
                    leaves,
                    sequence=sequence,
                )
            )
        return tuple(proofs)
