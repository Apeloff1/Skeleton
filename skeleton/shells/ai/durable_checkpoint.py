"""Signed checkpoints for long-lived durable evidence chains.

Checkpoints provide an externally signed commitment to a committed historical
root and sequence.  They are useful for archival, audits, and retention
planning.  They do not delete evidence and do not by themselves make pruning
safe; historical readers still require the underlying committed nodes unless an
archive-backed reader is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be SHA-256 hex"
        ) from exc
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
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_checkpoints,
        )

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
        return SignedDurableChainCheckpoint(
            checkpoint,
            signature,
            node.node_hash,
        )

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
