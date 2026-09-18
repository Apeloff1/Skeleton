"""Durable content-addressed execution receipt chain."""

from __future__ import annotations

from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceCorruption,
    EvidenceStateBackend,
    GENESIS_HASH,
)
from skeleton.shells.receipts import ChainedReceipt, ExecutionReceipt, ReceiptChain


class DistributedReceiptChain:
    """ReceiptChain-compatible facade backed by a CAS evidence store.

    The receipt hash intentionally uses the existing ReceiptChain hash function,
    preserving shell receipt semantics while node durability is delegated to the
    generic content-addressed evidence chain.
    """

    def __init__(
        self,
        backend: EvidenceStateBackend,
        *,
        namespace: str = "shell-receipts",
        max_receipts: int = 100_000,
    ) -> None:
        self.max_receipts = max_receipts
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_receipts,
        )

    @staticmethod
    def _payload(receipt: ExecutionReceipt) -> dict[str, object]:
        return receipt.to_dict()

    @staticmethod
    def _receipt(payload: dict[str, object]) -> ExecutionReceipt:
        return ExecutionReceipt(
            command=str(payload["command"]),
            correlation_id=str(payload["correlation_id"]),
            fingerprint=str(payload["fingerprint"]),
            started_at=str(payload["started_at"]),
            finished_at=str(payload["finished_at"]),
            duration_ms=float(payload["duration_ms"]),
            returncode=payload["returncode"],
            ok=bool(payload["ok"]),
            timed_out=bool(payload["timed_out"]),
            output_limited=bool(payload["output_limited"]),
            stdout_bytes=int(payload["stdout_bytes"]),
            stderr_bytes=int(payload["stderr_bytes"]),
            attempt=int(payload["attempt"]),
            receipt_id=str(payload["receipt_id"]),
            metadata=dict(payload.get("metadata", {})),
        )

    def append(self, receipt: ExecutionReceipt) -> ChainedReceipt:
        # Compute the committed shell receipt hash from the current durable root.
        # Store it inside the generic evidence payload, while the outer chain also
        # hashes the entire payload for content-addressed durability.
        payload = {
            "receipt": self._payload(receipt),
        }
        node = self._chain.append("shell.execution.receipt", payload)
        # A concurrent writer may have advanced the outer chain before this
        # append won CAS. Recalculate compatibility from the committed node.
        committed_receipt = self._receipt(dict(node.payload["receipt"]))
        committed_previous = self._committed_receipt_previous(node.sequence)
        committed_hash = ReceiptChain._hash(
            committed_previous,
            node.sequence,
            committed_receipt,
        )
        return ChainedReceipt(
            node.sequence,
            committed_previous,
            committed_hash,
            committed_receipt,
        )

    def _committed_receipt_previous(self, sequence: int) -> str:
        if sequence <= 1:
            return GENESIS_HASH
        items = self.snapshot()
        return items[sequence - 2].receipt_hash

    def snapshot(self) -> tuple[ChainedReceipt, ...]:
        nodes = self._chain.snapshot()
        result = []
        previous = GENESIS_HASH
        for node in nodes:
            raw = node.payload.get("receipt")
            if not isinstance(raw, dict):
                raise EvidenceCorruption("durable receipt payload is invalid")
            receipt = self._receipt(dict(raw))
            receipt_hash = ReceiptChain._hash(previous, node.sequence, receipt)
            result.append(
                ChainedReceipt(
                    node.sequence,
                    previous,
                    receipt_hash,
                    receipt,
                )
            )
            previous = receipt_hash
        return tuple(result)

    def verify(self) -> bool:
        if not self._chain.verify():
            return False
        try:
            items = self.snapshot()
        except (EvidenceCorruption, ValueError, KeyError, TypeError):
            return False
        previous = GENESIS_HASH
        for sequence, item in enumerate(items, start=1):
            if item.sequence != sequence or item.previous_hash != previous:
                return False
            if ReceiptChain._hash(previous, sequence, item.receipt) != item.receipt_hash:
                return False
            previous = item.receipt_hash
        return True

    def root_hash(self) -> str:
        items = self.snapshot()
        return items[-1].receipt_hash if items else GENESIS_HASH
