"""Bounded signed inclusion proofs for durable execution receipts.

The core receipt chain exposes an immutable receipt-id index and content-
addressed nodes, but an index lookup alone is not authority that the node is in
the committed chain. This module combines that candidate with the existing
signed checkpoint/proof-window infrastructure to prove commitment without
walking the entire live chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.durable_proof_window import (
    DurableHistoricalProofAuthority,
    DurableHistoricalProofError,
    DurableHistoricalProofStore,
    DurableHistoricalProofVerification,
    SignedDurableHistoricalProofWindow,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    ReceiptInclusion,
)


def _identity(name: str, value: str, *, maximum: int) -> str:
    if not value or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _digest(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
    return value.lower()


def _positive(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive integer")
    return value


class DurableReceiptInclusionState(str, Enum):
    VERIFIED = "verified"
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class DurableReceiptInclusionPolicy:
    require_receipt_index: bool = True
    require_current_ancestry: bool = True
    allow_build_proof: bool = True
    cache_built_proof: bool = True
    max_receipt_age_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "require_receipt_index",
            "require_current_ancestry",
            "allow_build_proof",
            "cache_built_proof",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if not self.require_current_ancestry:
            raise ValueError(
                "require_current_ancestry is a mandatory security invariant"
            )
        if self.cache_built_proof and not self.allow_build_proof:
            raise ValueError(
                "cache_built_proof requires allow_build_proof"
            )
        if self.max_receipt_age_seconds is not None:
            value = self.max_receipt_age_seconds
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(
                    "max_receipt_age_seconds must be finite and positive"
                )
            object.__setattr__(
                self,
                "max_receipt_age_seconds",
                float(value),
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
            "require_receipt_index": self.require_receipt_index,
            "require_current_ancestry": self.require_current_ancestry,
            "allow_build_proof": self.allow_build_proof,
            "cache_built_proof": self.cache_built_proof,
            "max_receipt_age_seconds": self.max_receipt_age_seconds,
        }


@dataclass(frozen=True)
class DurableReceiptInclusion:
    schema_version: int
    chain_id: str
    receipt_id: str
    receipt_fingerprint: str
    receipt_hash: str
    sequence: int
    proof: SignedDurableHistoricalProofWindow
    created_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported durable receipt inclusion schema")
        object.__setattr__(
            self,
            "chain_id",
            _identity("chain_id", self.chain_id, maximum=128),
        )
        object.__setattr__(
            self,
            "receipt_id",
            _identity("receipt_id", self.receipt_id, maximum=128),
        )
        object.__setattr__(
            self,
            "receipt_fingerprint",
            _digest("receipt_fingerprint", self.receipt_fingerprint),
        )
        object.__setattr__(
            self,
            "receipt_hash",
            _digest("receipt_hash", self.receipt_hash),
        )
        object.__setattr__(
            self,
            "sequence",
            _positive("sequence", self.sequence),
        )
        if not isinstance(
            self.proof,
            SignedDurableHistoricalProofWindow,
        ):
            raise TypeError(
                "proof must be SignedDurableHistoricalProofWindow"
            )
        if self.proof.proof.chain_id != self.chain_id:
            raise ValueError("proof chain_id differs from inclusion")
        if self.proof.proof.target_sequence != self.sequence:
            raise ValueError("proof target sequence differs from receipt")
        if self.proof.proof.target_root != self.receipt_hash:
            raise ValueError("proof target root differs from receipt")
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(float(self.created_at))
            or float(self.created_at) < 0.0
        ):
            raise ValueError("created_at must be finite and non-negative")
        object.__setattr__(self, "created_at", float(self.created_at))

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
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "receipt_id": self.receipt_id,
            "receipt_fingerprint": self.receipt_fingerprint,
            "receipt_hash": self.receipt_hash,
            "sequence": self.sequence,
            "proof": self.proof.to_dict(),
            "created_at": self.created_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableReceiptInclusionVerification:
    state: DurableReceiptInclusionState
    chain_id: str
    receipt_id: str
    sequence: int
    receipt_hash: str
    receipt_fingerprint: str
    current_sequence: int
    current_root: str
    indexed: bool
    node_valid: bool
    proof_valid: bool
    ancestor: bool
    proof_digest: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state",
            DurableReceiptInclusionState(self.state),
        )
        object.__setattr__(
            self,
            "chain_id",
            _identity("chain_id", self.chain_id, maximum=128),
        )
        object.__setattr__(
            self,
            "receipt_id",
            _identity("receipt_id", self.receipt_id, maximum=128),
        )
        object.__setattr__(
            self,
            "sequence",
            _positive("sequence", self.sequence),
        )
        object.__setattr__(
            self,
            "receipt_hash",
            _digest("receipt_hash", self.receipt_hash),
        )
        object.__setattr__(
            self,
            "receipt_fingerprint",
            _digest("receipt_fingerprint", self.receipt_fingerprint),
        )
        if (
            isinstance(self.current_sequence, bool)
            or not isinstance(self.current_sequence, int)
            or self.current_sequence < 0
        ):
            raise ValueError(
                "current_sequence must be non-negative integer"
            )
        object.__setattr__(
            self,
            "current_root",
            _digest("current_root", self.current_root),
        )
        for name in (
            "indexed",
            "node_valid",
            "proof_valid",
            "ancestor",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        object.__setattr__(
            self,
            "proof_digest",
            _digest("proof_digest", self.proof_digest),
        )
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if any(not reason or len(reason) > 2048 for reason in self.reasons):
            raise ValueError("invalid receipt inclusion reason")

    @property
    def valid(self) -> bool:
        return self.state is DurableReceiptInclusionState.VERIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "valid": self.valid,
            "chain_id": self.chain_id,
            "receipt_id": self.receipt_id,
            "sequence": self.sequence,
            "receipt_hash": self.receipt_hash,
            "receipt_fingerprint": self.receipt_fingerprint,
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "indexed": self.indexed,
            "node_valid": self.node_valid,
            "proof_valid": self.proof_valid,
            "ancestor": self.ancestor,
            "proof_digest": self.proof_digest,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DurableReceiptInclusionBatchResult:
    chain_id: str
    current_sequence: int
    current_root: str
    items: tuple[DurableReceiptInclusion, ...]
    verifications: tuple[
        DurableReceiptInclusionVerification,
        ...,
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "chain_id",
            _identity("chain_id", self.chain_id, maximum=128),
        )
        if (
            isinstance(self.current_sequence, bool)
            or not isinstance(self.current_sequence, int)
            or self.current_sequence < 0
        ):
            raise ValueError(
                "current_sequence must be non-negative integer"
            )
        object.__setattr__(
            self,
            "current_root",
            _digest("current_root", self.current_root),
        )
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(
            self,
            "verifications",
            tuple(self.verifications),
        )
        if len(self.items) != len(self.verifications):
            raise ValueError(
                "batch items/verifications length mismatch"
            )
        receipt_ids = tuple(
            item.receipt_id
            for item in self.items
        )
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError(
                "batch contains duplicate receipt_id"
            )
        for item, verification in zip(
            self.items,
            self.verifications,
            strict=True,
        ):
            if item.chain_id != self.chain_id:
                raise ValueError(
                    "batch item chain differs from batch"
                )
            if verification.chain_id != self.chain_id:
                raise ValueError(
                    "batch verification chain differs from batch"
                )
            if (
                verification.receipt_id
                != item.receipt_id
                or verification.receipt_hash
                != item.receipt_hash
                or verification.sequence
                != item.sequence
            ):
                raise ValueError(
                    "batch verification identity differs from item"
                )

    @property
    def valid(self) -> bool:
        return all(
            result.valid
            for result in self.verifications
        )

    @property
    def verified_count(self) -> int:
        return sum(
            1
            for result in self.verifications
            if result.valid
        )

    @property
    def invalid_count(self) -> int:
        return len(self.verifications) - self.verified_count

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
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "valid": self.valid,
            "verified_count": self.verified_count,
            "invalid_count": self.invalid_count,
            "items": [
                item.to_dict()
                for item in self.items
            ],
            "verifications": [
                item.to_dict()
                for item in self.verifications
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableReceiptInclusionError(RuntimeError):
    pass


class DurableReceiptInclusionAuthority:
    """Build and verify bounded signed receipt commitment proofs."""

    def __init__(
        self,
        proofs: DurableHistoricalProofAuthority,
        *,
        proof_store: DurableHistoricalProofStore | None = None,
        policy: DurableReceiptInclusionPolicy | None = None,
        clock: Callable[[], float] = time.time,
        max_batch_items: int = 512,
    ) -> None:
        if not isinstance(proofs, DurableHistoricalProofAuthority):
            raise TypeError(
                "proofs must be DurableHistoricalProofAuthority"
            )
        if proof_store is not None and not isinstance(
            proof_store,
            DurableHistoricalProofStore,
        ):
            raise TypeError(
                "proof_store must be DurableHistoricalProofStore"
            )
        if policy is not None and not isinstance(
            policy,
            DurableReceiptInclusionPolicy,
        ):
            raise TypeError(
                "policy must be DurableReceiptInclusionPolicy"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if (
            isinstance(max_batch_items, bool)
            or not isinstance(max_batch_items, int)
            or max_batch_items <= 0
        ):
            raise ValueError(
                "max_batch_items must be positive integer"
            )
        self.proofs = proofs
        self.proof_store = proof_store
        self.policy = policy or DurableReceiptInclusionPolicy()
        self._clock = clock
        self.max_batch_items = max_batch_items

    @staticmethod
    def _require_chain(chain: object) -> DistributedReceiptChain:
        if not isinstance(chain, DistributedReceiptChain):
            raise TypeError(
                "chain must be DistributedReceiptChain"
            )
        return chain

    def _candidate(
        self,
        chain: DistributedReceiptChain,
        receipt_id: str,
    ) -> ReceiptInclusion:
        receipt_id = _identity(
            "receipt_id",
            receipt_id,
            maximum=128,
        )
        candidate = chain.indexed_receipt(
            receipt_id,
            repair_missing=False,
        )
        if candidate is None:
            raise DurableReceiptInclusionError(
                "receipt index is missing or compacted"
            )
        return candidate

    def _proof_for(
        self,
        chain_id: str,
        chain: DistributedReceiptChain,
        candidate: ReceiptInclusion,
    ) -> SignedDurableHistoricalProofWindow:
        cached = None
        if self.proof_store is not None:
            cached = self.proof_store.find_target(
                chain_id,
                candidate.entry.receipt_hash,
            )
        if cached is not None:
            return cached
        if not self.policy.allow_build_proof:
            raise DurableReceiptInclusionError(
                "receipt proof is not cached and policy forbids building"
            )
        try:
            built = self.proofs.build_for_sequence(
                chain_id,
                chain,
                candidate.entry.sequence,
            )
        except DurableHistoricalProofError as exc:
            raise DurableReceiptInclusionError(
                "receipt proof could not be built"
            ) from exc
        if (
            self.proof_store is not None
            and self.policy.cache_built_proof
        ):
            return self.proof_store.put_once_for_target(
                built
            )
        return built

    def build(
        self,
        chain_id: str,
        chain: object,
        receipt_id: str,
    ) -> DurableReceiptInclusion:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        chain = self._require_chain(chain)
        candidate = self._candidate(
            chain,
            receipt_id,
        )
        proof = self._proof_for(
            chain_id,
            chain,
            candidate,
        )
        if (
            proof.proof.target_sequence
            != candidate.entry.sequence
            or proof.proof.target_root
            != candidate.entry.receipt_hash
        ):
            raise DurableReceiptInclusionError(
                "receipt proof target differs from indexed candidate"
            )
        try:
            proof_verification = self.proofs.require(
                proof,
                chain,
            )
        except DurableHistoricalProofError as exc:
            raise DurableReceiptInclusionError(
                "receipt proof failed verification"
            ) from exc
        if not proof_verification.valid:
            raise DurableReceiptInclusionError(
                "receipt proof is invalid"
            )
        if (
            self.policy.require_current_ancestry
            and not chain.root_is_ancestor(
                candidate.entry.receipt_hash
            )
        ):
            raise DurableReceiptInclusionError(
                "receipt proof target is not an ancestor of committed head"
            )
        created_at = self._clock()
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(float(created_at))
            or float(created_at) < 0.0
        ):
            raise DurableReceiptInclusionError(
                "receipt inclusion clock returned invalid time"
            )
        return DurableReceiptInclusion(
            1,
            chain_id,
            candidate.entry.receipt_id,
            candidate.entry.receipt_fingerprint,
            candidate.entry.receipt_hash,
            candidate.entry.sequence,
            proof,
            float(created_at),
        )

    def _verify_internal(
        self,
        item: DurableReceiptInclusion,
        chain: DistributedReceiptChain,
        *,
        ancestor_override: bool | None = None,
    ) -> DurableReceiptInclusionVerification:
        if not isinstance(item, DurableReceiptInclusion):
            raise TypeError(
                "item must be DurableReceiptInclusion"
            )
        head = chain.head()
        reasons: list[str] = []
        indexed = False
        node_valid = False
        proof_valid = False
        ancestor = False

        try:
            node = chain.get_node(
                item.receipt_hash
            )
            node_valid = (
                node.sequence == item.sequence
                and node.receipt.receipt_id
                == item.receipt_id
                and node.receipt.fingerprint
                == item.receipt_fingerprint
                and node.receipt_hash
                == item.receipt_hash
            )
            if not node_valid:
                reasons.append(
                    "receipt node identity differs from inclusion"
                )
        except Exception:
            reasons.append(
                "receipt node is missing or corrupt"
            )

        try:
            candidate = chain.indexed_receipt(
                item.receipt_id,
                repair_missing=False,
            )
            if candidate is not None:
                indexed = (
                    candidate.entry.sequence
                    == item.sequence
                    and candidate.entry.receipt_hash
                    == item.receipt_hash
                    and candidate.entry.receipt_fingerprint
                    == item.receipt_fingerprint
                )
            if (
                self.policy.require_receipt_index
                and not indexed
            ):
                reasons.append(
                    "receipt index does not bind inclusion"
                )
        except Exception:
            if self.policy.require_receipt_index:
                reasons.append(
                    "receipt index is unavailable or corrupt"
                )

        proof_result: DurableHistoricalProofVerification | None = None
        try:
            proof_result = self.proofs.verify(
                item.proof,
                chain,
            )
            proof_valid = proof_result.valid
            if not proof_valid:
                reasons.extend(
                    f"proof: {reason}"
                    for reason in proof_result.reasons
                )
        except Exception:
            reasons.append(
                "receipt proof verification raised an error"
            )

        if (
            item.proof.proof.target_sequence
            != item.sequence
        ):
            reasons.append(
                "proof target sequence differs from inclusion"
            )
        if (
            item.proof.proof.target_root
            != item.receipt_hash
        ):
            reasons.append(
                "proof target root differs from inclusion"
            )
        if (
            item.proof.proof.chain_id
            != item.chain_id
        ):
            reasons.append(
                "proof chain differs from inclusion"
            )

        if ancestor_override is None:
            try:
                ancestor = chain.root_is_ancestor(
                    item.receipt_hash
                )
            except Exception:
                ancestor = False
        else:
            ancestor = bool(ancestor_override)
        if (
            self.policy.require_current_ancestry
            and not ancestor
        ):
            reasons.append(
                "receipt target is not committed ancestor"
            )

        if (
            item.sequence > int(head.sequence)
        ):
            reasons.append(
                "receipt sequence exceeds committed head"
            )

        if self.policy.max_receipt_age_seconds is not None:
            age = float(self._clock()) - item.created_at
            if (
                not math.isfinite(age)
                or age < 0.0
                or age > self.policy.max_receipt_age_seconds
            ):
                reasons.append(
                    "receipt inclusion proof is stale"
                )

        if not reasons:
            state = DurableReceiptInclusionState.VERIFIED
        elif any("stale" in reason for reason in reasons):
            state = DurableReceiptInclusionState.STALE
        elif any(
            phrase in reason
            for reason in reasons
            for phrase in (
                "corrupt",
                "differs",
                "does not bind",
                "not committed ancestor",
            )
        ):
            state = DurableReceiptInclusionState.MANUAL_REVIEW
        elif any("missing" in reason for reason in reasons):
            state = DurableReceiptInclusionState.MISSING
        else:
            state = DurableReceiptInclusionState.INVALID

        return DurableReceiptInclusionVerification(
            state,
            item.chain_id,
            item.receipt_id,
            item.sequence,
            item.receipt_hash,
            item.receipt_fingerprint,
            int(head.sequence),
            str(head.root_hash),
            indexed,
            node_valid,
            proof_valid,
            ancestor,
            item.proof.proof.digest,
            tuple(reasons),
        )

    def verify(
        self,
        item: DurableReceiptInclusion,
        chain: object,
    ) -> DurableReceiptInclusionVerification:
        if not isinstance(item, DurableReceiptInclusion):
            raise TypeError(
                "item must be DurableReceiptInclusion"
            )
        chain = self._require_chain(chain)
        return self._verify_internal(
            item,
            chain,
        )

    def require(
        self,
        item: DurableReceiptInclusion,
        chain: object,
    ) -> DurableReceiptInclusionVerification:
        result = self.verify(
            item,
            chain,
        )
        if not result.valid:
            detail = (
                result.reasons[0]
                if result.reasons
                else "receipt inclusion verification failed"
            )
            raise DurableReceiptInclusionError(
                detail
            )
        return result

    def _batch_receipt_ids(
        self,
        receipt_ids,
    ) -> tuple[str, ...]:
        values = tuple(receipt_ids)
        if len(values) > self.max_batch_items:
            raise DurableReceiptInclusionError(
                "receipt inclusion batch exceeds configured bound"
            )
        normalized = tuple(
            _identity(
                "receipt_id",
                value,
                maximum=128,
            )
            for value in values
        )
        if len(normalized) != len(set(normalized)):
            raise DurableReceiptInclusionError(
                "receipt inclusion batch contains duplicates"
            )
        return normalized

    def _committed_root_set(
        self,
        chain: DistributedReceiptChain,
    ) -> tuple[int, str, frozenset[str]]:
        try:
            snapshot = chain.snapshot()
        except Exception as exc:
            raise DurableReceiptInclusionError(
                "committed receipt chain snapshot failed"
            ) from exc
        head = chain.head()
        roots = frozenset(
            item.receipt_hash
            for item in snapshot
        )
        return (
            int(head.sequence),
            str(head.root_hash),
            roots,
        )

    def build_many(
        self,
        chain_id: str,
        chain: object,
        receipt_ids,
    ) -> DurableReceiptInclusionBatchResult:
        chain_id = _identity(
            "chain_id",
            chain_id,
            maximum=128,
        )
        chain = self._require_chain(chain)
        values = self._batch_receipt_ids(
            receipt_ids
        )
        (
            current_sequence,
            current_root,
            committed_roots,
        ) = self._committed_root_set(chain)

        items: list[DurableReceiptInclusion] = []
        results: list[
            DurableReceiptInclusionVerification
        ] = []
        for receipt_id in values:
            candidate = self._candidate(
                chain,
                receipt_id,
            )
            if (
                candidate.entry.receipt_hash
                not in committed_roots
            ):
                raise DurableReceiptInclusionError(
                    "indexed receipt is not in committed chain snapshot"
                )
            proof = self._proof_for(
                chain_id,
                chain,
                candidate,
            )
            if (
                proof.proof.target_sequence
                != candidate.entry.sequence
                or proof.proof.target_root
                != candidate.entry.receipt_hash
            ):
                raise DurableReceiptInclusionError(
                    "receipt proof target differs from indexed candidate"
                )
            try:
                self.proofs.require(
                    proof,
                    chain,
                )
            except DurableHistoricalProofError as exc:
                raise DurableReceiptInclusionError(
                    "receipt proof failed verification"
                ) from exc
            now = self._clock()
            if (
                isinstance(now, bool)
                or not isinstance(now, (int, float))
                or not math.isfinite(float(now))
                or float(now) < 0.0
            ):
                raise DurableReceiptInclusionError(
                    "receipt inclusion clock returned invalid time"
                )
            item = DurableReceiptInclusion(
                1,
                chain_id,
                candidate.entry.receipt_id,
                candidate.entry.receipt_fingerprint,
                candidate.entry.receipt_hash,
                candidate.entry.sequence,
                proof,
                float(now),
            )
            result = self._verify_internal(
                item,
                chain,
                ancestor_override=True,
            )
            items.append(item)
            results.append(result)

        return DurableReceiptInclusionBatchResult(
            chain_id,
            current_sequence,
            current_root,
            tuple(items),
            tuple(results),
        )

    def verify_many(
        self,
        items,
        chain: object,
    ) -> DurableReceiptInclusionBatchResult:
        values = tuple(items)
        if len(values) > self.max_batch_items:
            raise DurableReceiptInclusionError(
                "receipt inclusion batch exceeds configured bound"
            )
        if any(
            not isinstance(
                item,
                DurableReceiptInclusion,
            )
            for item in values
        ):
            raise TypeError(
                "all batch items must be DurableReceiptInclusion"
            )
        chain = self._require_chain(chain)
        chain_ids = {
            item.chain_id
            for item in values
        }
        if len(chain_ids) > 1:
            raise DurableReceiptInclusionError(
                "receipt inclusion batch mixes chain identities"
            )
        chain_id = (
            next(iter(chain_ids))
            if chain_ids
            else "receipts"
        )
        receipt_ids = tuple(
            item.receipt_id
            for item in values
        )
        if len(receipt_ids) != len(set(receipt_ids)):
            raise DurableReceiptInclusionError(
                "receipt inclusion batch contains duplicates"
            )
        (
            current_sequence,
            current_root,
            committed_roots,
        ) = self._committed_root_set(chain)
        results = tuple(
            self._verify_internal(
                item,
                chain,
                ancestor_override=(
                    item.receipt_hash
                    in committed_roots
                ),
            )
            for item in values
        )
        return DurableReceiptInclusionBatchResult(
            chain_id,
            current_sequence,
            current_root,
            values,
            results,
        )

    def require_many(
        self,
        items,
        chain: object,
    ) -> DurableReceiptInclusionBatchResult:
        result = self.verify_many(
            items,
            chain,
        )
        if not result.valid:
            first = next(
                (
                    verification
                    for verification
                    in result.verifications
                    if not verification.valid
                ),
                None,
            )
            detail = (
                first.reasons[0]
                if first is not None
                and first.reasons
                else "receipt inclusion batch verification failed"
            )
            raise DurableReceiptInclusionError(
                detail
            )
        return result

    def build_and_require(
        self,
        chain_id: str,
        chain: object,
        receipt_id: str,
    ) -> tuple[
        DurableReceiptInclusion,
        DurableReceiptInclusionVerification,
    ]:
        item = self.build(
            chain_id,
            chain,
            receipt_id,
        )
        return item, self.require(
            item,
            chain,
        )
