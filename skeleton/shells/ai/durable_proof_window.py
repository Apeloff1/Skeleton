"""Signed bounded historical proof windows for durable evidence chains.

Long-lived durable chains should not require a genesis-to-target walk for every
historical recovery check.  A proof window anchors a target historical root to
an already signed durable checkpoint and commits the exact bounded hash-linked
segment between them.

The underlying chain and checkpoint registry remain authoritative.  Proof
windows are acceleration artifacts only: verification rechecks the canonical
checkpoint, exact sequence locators, committed target root, and bounded segment
content with sequence-index repair disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable, Protocol, runtime_checkable

from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
    SignedDurableChainCheckpoint,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.ai.distributed_state import DistributedStateConflict


PROOF_ARTIFACT_TYPE = "shell-ai-durable-proof-window"


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
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


def _sequence(
    name: str,
    value: int,
    *,
    allow_zero: bool = True,
) -> int:
    minimum = 0 if allow_zero else 1
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise ValueError(
            f"{name} must be integer >= {minimum}"
        )
    return value


def _item_hash(item: object) -> str:
    for name in (
        "event_hash",
        "receipt_hash",
        "node_hash",
    ):
        value = getattr(item, name, None)
        if isinstance(value, str) and len(value) == 64:
            return _digest(name, value)
    raise TypeError(
        "proof-window item has no supported hash attribute"
    )


def _previous_hash(item: object) -> str:
    value = getattr(item, "previous_hash", None)
    if not isinstance(value, str):
        raise TypeError(
            "proof-window item has no previous_hash"
        )
    return _digest(
        "previous_hash",
        value,
    )


def _item_sequence(item: object) -> int:
    return _sequence(
        "item sequence",
        getattr(item, "sequence", None),
        allow_zero=False,
    )


def _segment_commitments(
    items: tuple[object, ...],
) -> tuple[tuple[int, str, str], ...]:
    return tuple(
        (
            _item_sequence(item),
            _previous_hash(item),
            _item_hash(item),
        )
        for item in items
    )


def _segment_digest(
    commitments: tuple[
        tuple[int, str, str],
        ...,
    ],
) -> str:
    raw = json.dumps(
        [
            {
                "sequence": sequence,
                "previous_hash": previous,
                "item_hash": item_hash,
            }
            for (
                sequence,
                previous,
                item_hash,
            ) in commitments
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@runtime_checkable
class ProofWindowChain(Protocol):
    def head(self): ...

    def hot_floor(self): ...

    def root_for_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> str: ...

    def snapshot_range(
        self,
        start_sequence: int,
        end_sequence: int,
        *,
        max_items: int = 4096,
        repair_missing: bool = True,
    ) -> tuple[object, ...]: ...

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool: ...


@dataclass(frozen=True)
class DurableHistoricalProofWindow:
    schema_version: int
    chain_id: str
    checkpoint_digest: str
    checkpoint_sequence: int
    checkpoint_root: str
    target_sequence: int
    target_root: str
    item_count: int
    segment_digest: str
    first_item_hash: str
    last_item_hash: str
    generated_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported historical proof-window schema"
            )
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        for name in (
            "checkpoint_digest",
            "checkpoint_root",
            "target_root",
            "segment_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "first_item_hash",
            "last_item_hash",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        object.__setattr__(
            self,
            "checkpoint_sequence",
            _sequence(
                "checkpoint_sequence",
                self.checkpoint_sequence,
            ),
        )
        object.__setattr__(
            self,
            "target_sequence",
            _sequence(
                "target_sequence",
                self.target_sequence,
            ),
        )
        object.__setattr__(
            self,
            "item_count",
            _sequence(
                "item_count",
                self.item_count,
            ),
        )
        if self.target_sequence < self.checkpoint_sequence:
            raise ValueError(
                "proof target precedes checkpoint anchor"
            )
        expected_count = (
            self.target_sequence
            - self.checkpoint_sequence
        )
        if self.item_count != expected_count:
            raise ValueError(
                "proof item_count differs from sequence distance"
            )
        if self.item_count == 0:
            if self.target_root != self.checkpoint_root:
                raise ValueError(
                    "zero-length proof must target checkpoint root"
                )
            if self.first_item_hash or self.last_item_hash:
                raise ValueError(
                    "zero-length proof may not bind item hashes"
                )
        else:
            if not self.first_item_hash or not self.last_item_hash:
                raise ValueError(
                    "non-empty proof requires boundary item hashes"
                )
            if self.last_item_hash != self.target_root:
                raise ValueError(
                    "proof last item must equal target root"
                )
        if (
            isinstance(self.generated_at, bool)
            or not isinstance(
                self.generated_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.generated_at)
            )
            or float(self.generated_at) < 0.0
        ):
            raise ValueError(
                "generated_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "generated_at",
            float(self.generated_at),
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "checkpoint_digest": self.checkpoint_digest,
            "checkpoint_sequence": self.checkpoint_sequence,
            "checkpoint_root": self.checkpoint_root,
            "target_sequence": self.target_sequence,
            "target_root": self.target_root,
            "item_count": self.item_count,
            "segment_digest": self.segment_digest,
            "first_item_hash": self.first_item_hash,
            "last_item_hash": self.last_item_hash,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class SignedDurableHistoricalProofWindow:
    proof: DurableHistoricalProofWindow
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.proof,
            DurableHistoricalProofWindow,
        ):
            raise TypeError(
                "proof must be DurableHistoricalProofWindow"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "proof": self.proof.to_dict(),
            "proof_digest": self.proof.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableHistoricalProofVerification:
    valid: bool
    chain_id: str
    target_sequence: int
    target_root: str
    checkpoint_sequence: int
    checkpoint_root: str
    checked_items: int
    current_sequence: int
    current_root: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.valid, bool):
            raise ValueError("valid must be bool")
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        for name in (
            "target_sequence",
            "checkpoint_sequence",
            "checked_items",
            "current_sequence",
        ):
            object.__setattr__(
                self,
                name,
                _sequence(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "target_root",
            "checkpoint_root",
            "current_root",
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
            "reasons",
            tuple(self.reasons),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "chain_id": self.chain_id,
            "target_sequence": self.target_sequence,
            "target_root": self.target_root,
            "checkpoint_sequence": self.checkpoint_sequence,
            "checkpoint_root": self.checkpoint_root,
            "checked_items": self.checked_items,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "reasons": list(self.reasons),
        }


class DurableHistoricalProofError(RuntimeError):
    pass


class DurableHistoricalProofAuthority:
    """Build and verify bounded proofs anchored to signed checkpoints."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        signer: ArtifactSigner,
        *,
        max_window_items: int = 4096,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            checkpoints,
            DurableChainCheckpointStore,
        ):
            raise TypeError(
                "checkpoints must be DurableChainCheckpointStore"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        if (
            isinstance(max_window_items, bool)
            or not isinstance(
                max_window_items,
                int,
            )
            or max_window_items <= 0
        ):
            raise ValueError(
                "max_window_items must be positive integer"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.checkpoints = checkpoints
        self.signer = signer
        self.max_window_items = max_window_items
        self._clock = clock

    @staticmethod
    def _require_chain(
        chain: object,
    ) -> ProofWindowChain:
        if not isinstance(
            chain,
            ProofWindowChain,
        ):
            raise TypeError(
                "chain does not support proof-window operations"
            )
        return chain

    @staticmethod
    def _hot_floor_sequence(
        chain: ProofWindowChain,
    ) -> int:
        floor = chain.hot_floor()
        return int(
            getattr(floor, "sequence", 0)
        )

    def _select_checkpoint(
        self,
        chain_id: str,
        chain: ProofWindowChain,
        target_sequence: int,
    ) -> SignedDurableChainCheckpoint:
        if not self.checkpoints.verify():
            raise DurableHistoricalProofError(
                "checkpoint registry failed integrity"
            )
        floor_sequence = (
            self._hot_floor_sequence(
                chain
            )
        )
        candidates = tuple(
            item
            for item in self.checkpoints.for_chain(
                chain_id
            )
            if (
                floor_sequence
                <= item.checkpoint.sequence
                <= target_sequence
            )
        )
        if not candidates:
            raise DurableHistoricalProofError(
                "no signed checkpoint can anchor bounded target proof"
            )
        checkpoint = max(
            candidates,
            key=lambda item: (
                item.checkpoint.sequence
            ),
        )
        canonical = (
            self.checkpoints.find_by_digest(
                checkpoint.checkpoint.digest
            )
        )
        if canonical != checkpoint:
            raise DurableHistoricalProofError(
                "selected checkpoint is not canonical"
            )
        return checkpoint

    def build_for_sequence(
        self,
        chain_id: str,
        chain: object,
        target_sequence: int,
    ) -> SignedDurableHistoricalProofWindow:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        chain = self._require_chain(
            chain
        )
        target_sequence = _sequence(
            "target_sequence",
            target_sequence,
        )
        head = chain.head()
        current_sequence = int(
            head.sequence
        )
        if target_sequence > current_sequence:
            raise DurableHistoricalProofError(
                "proof target exceeds committed chain head"
            )
        checkpoint = self._select_checkpoint(
            chain_id,
            chain,
            target_sequence,
        )
        anchor = checkpoint.checkpoint
        distance = (
            target_sequence
            - anchor.sequence
        )
        if distance > self.max_window_items:
            raise DurableHistoricalProofError(
                "target exceeds bounded proof-window size"
            )

        try:
            canonical_anchor_root = (
                chain.root_for_sequence(
                    anchor.sequence,
                    repair_missing=False,
                )
            )
        except Exception as exc:
            raise DurableHistoricalProofError(
                "checkpoint sequence locator is unavailable"
            ) from exc
        if (
            canonical_anchor_root
            != anchor.root_hash
        ):
            raise DurableHistoricalProofError(
                "checkpoint root differs from canonical sequence locator"
            )

        try:
            target_root = (
                chain.root_for_sequence(
                    target_sequence,
                    repair_missing=False,
                )
            )
        except Exception as exc:
            raise DurableHistoricalProofError(
                "target sequence locator is unavailable"
            ) from exc

        if distance == 0:
            items: tuple[object, ...] = ()
        else:
            try:
                items = chain.snapshot_range(
                    anchor.sequence + 1,
                    target_sequence,
                    max_items=(
                        self.max_window_items
                    ),
                    repair_missing=False,
                )
            except Exception as exc:
                raise DurableHistoricalProofError(
                    "bounded proof segment could not be reconstructed"
                ) from exc

        commitments = _segment_commitments(
            tuple(items)
        )
        if len(commitments) != distance:
            raise DurableHistoricalProofError(
                "bounded proof segment length mismatch"
            )
        if commitments:
            first_hash = commitments[0][2]
            last_hash = commitments[-1][2]
            if commitments[0][1] != anchor.root_hash:
                raise DurableHistoricalProofError(
                    "proof segment does not descend from checkpoint root"
                )
            if last_hash != target_root:
                raise DurableHistoricalProofError(
                    "proof segment does not terminate at target root"
                )
        else:
            first_hash = ""
            last_hash = ""
            if target_root != anchor.root_hash:
                raise DurableHistoricalProofError(
                    "zero-length proof target differs from checkpoint"
                )

        proof = DurableHistoricalProofWindow(
            1,
            chain_id,
            anchor.digest,
            anchor.sequence,
            anchor.root_hash,
            target_sequence,
            target_root,
            distance,
            _segment_digest(
                commitments
            ),
            first_hash,
            last_hash,
            float(self._clock()),
        )
        signature = self.signer.sign(
            PROOF_ARTIFACT_TYPE,
            proof.digest,
            metadata={
                "chain_id": chain_id,
                "target_sequence": str(
                    target_sequence
                ),
                "checkpoint_sequence": str(
                    anchor.sequence
                ),
            },
        )
        return SignedDurableHistoricalProofWindow(
            proof,
            signature,
        )

    def build_for_root(
        self,
        chain_id: str,
        chain: object,
        target_root: str,
    ) -> SignedDurableHistoricalProofWindow:
        chain = self._require_chain(
            chain
        )
        target_root = _digest(
            "target_root",
            target_root,
        )
        try:
            sequence = int(
                chain.sequence_for_root(
                    target_root
                )
            )
        except AttributeError as exc:
            raise TypeError(
                "chain does not expose sequence_for_root"
            ) from exc
        except Exception as exc:
            raise DurableHistoricalProofError(
                "target root does not resolve to sequence"
            ) from exc
        item = self.build_for_sequence(
            chain_id,
            chain,
            sequence,
        )
        if item.proof.target_root != target_root:
            raise DurableHistoricalProofError(
                "target root/sequence locator mismatch"
            )
        return item

    def verify(
        self,
        item: SignedDurableHistoricalProofWindow,
        chain: object,
    ) -> DurableHistoricalProofVerification:
        if not isinstance(
            item,
            SignedDurableHistoricalProofWindow,
        ):
            raise TypeError(
                "item must be SignedDurableHistoricalProofWindow"
            )
        chain = self._require_chain(
            chain
        )
        proof = item.proof
        reasons: list[str] = []

        if (
            item.signature.artifact_type
            != PROOF_ARTIFACT_TYPE
        ):
            reasons.append(
                "proof artifact type is invalid"
            )
        if (
            item.signature.artifact_digest
            != proof.digest
        ):
            reasons.append(
                "proof signature digest differs from proof"
            )
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError:
            reasons.append(
                "proof signature is invalid"
            )

        checkpoint = None
        if not self.checkpoints.verify():
            reasons.append(
                "checkpoint registry failed integrity"
            )
        else:
            try:
                checkpoint = (
                    self.checkpoints
                    .find_by_digest(
                        proof.checkpoint_digest
                    )
                )
            except Exception:
                checkpoint = None
                reasons.append(
                    "checkpoint lookup failed"
                )
        if checkpoint is None:
            reasons.append(
                "proof checkpoint is missing"
            )
        else:
            anchor = checkpoint.checkpoint
            if anchor.chain_id != proof.chain_id:
                reasons.append(
                    "proof checkpoint chain differs"
                )
            if (
                anchor.sequence
                != proof.checkpoint_sequence
            ):
                reasons.append(
                    "proof checkpoint sequence differs"
                )
            if (
                anchor.root_hash
                != proof.checkpoint_root
            ):
                reasons.append(
                    "proof checkpoint root differs"
                )

        head = chain.head()
        current_sequence = int(
            head.sequence
        )
        current_root = _digest(
            "current_root",
            str(head.root_hash),
        )
        if (
            proof.target_sequence
            > current_sequence
        ):
            reasons.append(
                "proof target exceeds current committed head"
            )

        checked_items = 0
        if (
            proof.item_count
            > self.max_window_items
        ):
            reasons.append(
                "proof exceeds verifier window bound"
            )
        else:
            try:
                anchor_root = (
                    chain.root_for_sequence(
                        proof.checkpoint_sequence,
                        repair_missing=False,
                    )
                )
                target_root = (
                    chain.root_for_sequence(
                        proof.target_sequence,
                        repair_missing=False,
                    )
                )
            except Exception:
                anchor_root = ""
                target_root = ""
                reasons.append(
                    "proof sequence locators are unavailable"
                )
            if (
                anchor_root
                and anchor_root
                != proof.checkpoint_root
            ):
                reasons.append(
                    "canonical checkpoint sequence root differs"
                )
            if (
                target_root
                and target_root
                != proof.target_root
            ):
                reasons.append(
                    "canonical target sequence root differs"
                )

            if (
                not reasons
                or all(
                    reason
                    not in {
                        "proof sequence locators are unavailable",
                        "canonical checkpoint sequence root differs",
                        "canonical target sequence root differs",
                    }
                    for reason in reasons
                )
            ):
                if proof.item_count == 0:
                    items: tuple[object, ...] = ()
                else:
                    try:
                        items = (
                            chain.snapshot_range(
                                proof.checkpoint_sequence
                                + 1,
                                proof.target_sequence,
                                max_items=(
                                    self.max_window_items
                                ),
                                repair_missing=False,
                            )
                        )
                    except Exception:
                        items = ()
                        reasons.append(
                            "bounded proof segment reconstruction failed"
                        )
                commitments = (
                    _segment_commitments(
                        tuple(items)
                    )
                )
                checked_items = len(
                    commitments
                )
                if (
                    checked_items
                    != proof.item_count
                ):
                    reasons.append(
                        "proof segment item count differs"
                    )
                if (
                    _segment_digest(
                        commitments
                    )
                    != proof.segment_digest
                ):
                    reasons.append(
                        "proof segment digest differs"
                    )
                if commitments:
                    if (
                        commitments[0][1]
                        != proof.checkpoint_root
                    ):
                        reasons.append(
                            "proof segment no longer descends from checkpoint"
                        )
                    if (
                        commitments[0][2]
                        != proof.first_item_hash
                    ):
                        reasons.append(
                            "proof first item hash differs"
                        )
                    if (
                        commitments[-1][2]
                        != proof.last_item_hash
                    ):
                        reasons.append(
                            "proof last item hash differs"
                        )
                elif (
                    proof.first_item_hash
                    or proof.last_item_hash
                ):
                    reasons.append(
                        "empty proof unexpectedly binds item hashes"
                    )

        return DurableHistoricalProofVerification(
            not reasons,
            proof.chain_id,
            proof.target_sequence,
            proof.target_root,
            proof.checkpoint_sequence,
            proof.checkpoint_root,
            checked_items,
            current_sequence,
            current_root,
            tuple(reasons),
        )

    def require(
        self,
        item: SignedDurableHistoricalProofWindow,
        chain: object,
    ) -> DurableHistoricalProofVerification:
        result = self.verify(
            item,
            chain,
        )
        if not result.valid:
            detail = (
                result.reasons[0]
                if result.reasons
                else "historical proof-window verification failed"
            )
            raise DurableHistoricalProofError(
                detail
            )
        return result


@dataclass(frozen=True)
class DurableHistoricalProofIndex:
    chain_id: str
    target_sequence: int
    target_root: str
    proof_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity(
                "chain_id",
                self.chain_id,
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "target_sequence",
            _sequence(
                "target_sequence",
                self.target_sequence,
            ),
        )
        for name in (
            "target_root",
            "proof_digest",
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
            "target_sequence": self.target_sequence,
            "target_root": self.target_root,
            "proof_digest": self.proof_digest,
        }


class DurableHistoricalProofStore:
    """Immutable proof cache with exact target-root and digest indexes."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-durable-proof-window",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable proof-window namespace"
            )
        self.backend = backend
        self.namespace = namespace

    @staticmethod
    def _proof_key(
        proof_digest: str,
    ) -> str:
        return "proof:" + _digest(
            "proof_digest",
            proof_digest,
        )

    @staticmethod
    def _target_key(
        chain_id: str,
        target_root: str,
    ) -> str:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        target_root = _digest(
            "target_root",
            target_root,
        )
        raw = json.dumps(
            {
                "chain_id": chain_id,
                "target_root": target_root,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return (
            "target:"
            + hashlib.sha256(raw).hexdigest()
        )

    @staticmethod
    def _index_for(
        item: SignedDurableHistoricalProofWindow,
    ) -> DurableHistoricalProofIndex:
        return DurableHistoricalProofIndex(
            item.proof.chain_id,
            item.proof.target_sequence,
            item.proof.target_root,
            item.proof.digest,
        )

    def _put_exact(
        self,
        key: str,
        value: object,
    ):
        current = self.backend.get(
            self.namespace,
            key,
        )
        if current is None:
            try:
                return self.backend.put_if_absent(
                    self.namespace,
                    key,
                    value,
                )
            except DistributedStateConflict:
                current = self.backend.get(
                    self.namespace,
                    key,
                )
                if current is None:
                    raise
        if current.value != value:
            raise DurableHistoricalProofError(
                "proof-window key already binds different value"
            )
        return current

    def put(
        self,
        item: SignedDurableHistoricalProofWindow,
    ) -> int:
        if not isinstance(
            item,
            SignedDurableHistoricalProofWindow,
        ):
            raise TypeError(
                "item must be SignedDurableHistoricalProofWindow"
            )
        proof_record = self._put_exact(
            self._proof_key(
                item.proof.digest
            ),
            item,
        )
        index = self._index_for(
            item
        )
        self._put_exact(
            self._target_key(
                index.chain_id,
                index.target_root,
            ),
            index,
        )
        return int(
            proof_record.revision
        )

    def get(
        self,
        proof_digest: str,
    ) -> SignedDurableHistoricalProofWindow | None:
        record = self.backend.get(
            self.namespace,
            self._proof_key(
                proof_digest
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableHistoricalProofWindow,
        ):
            raise DurableHistoricalProofError(
                "proof-window record has invalid type"
            )
        item = record.value
        if (
            item.proof.digest
            != _digest(
                "proof_digest",
                proof_digest,
            )
        ):
            raise DurableHistoricalProofError(
                "proof-window key/digest mismatch"
            )
        return item

    def find_target(
        self,
        chain_id: str,
        target_root: str,
    ) -> SignedDurableHistoricalProofWindow | None:
        key = self._target_key(
            chain_id,
            target_root,
        )
        record = self.backend.get(
            self.namespace,
            key,
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableHistoricalProofIndex,
        ):
            raise DurableHistoricalProofError(
                "proof-window target index has invalid type"
            )
        index = record.value
        if (
            index.chain_id != chain_id
            or index.target_root
            != _digest(
                "target_root",
                target_root,
            )
        ):
            raise DurableHistoricalProofError(
                "proof-window target index identity mismatch"
            )
        item = self.get(
            index.proof_digest
        )
        if item is None:
            raise DurableHistoricalProofError(
                "proof-window target index references missing proof"
            )
        if (
            item.proof.target_sequence
            != index.target_sequence
            or item.proof.target_root
            != index.target_root
        ):
            raise DurableHistoricalProofError(
                "proof-window target index/proof mismatch"
            )
        return item

    def put_once_for_target(
        self,
        item: SignedDurableHistoricalProofWindow,
    ) -> SignedDurableHistoricalProofWindow:
        existing = self.find_target(
            item.proof.chain_id,
            item.proof.target_root,
        )
        if existing is not None:
            if (
                existing.proof.digest
                != item.proof.digest
            ):
                raise DurableHistoricalProofError(
                    "target root already binds different proof"
                )
            return existing
        self.put(
            item
        )
        return item
