"""Compatibility import for the durable distributed receipt chain.

The canonical implementation lives in skeleton.shells.distributed_receipts.
This module preserves the established skeleton.shells.durable_receipts import
path for downstream callers.
"""

from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptConflict,
    DistributedReceiptCorruption,
    DistributedReceiptHead,
    GENESIS_HASH,
    ReceiptInclusion,
    ReceiptIndexEntry,
)

__all__ = [
    "DistributedReceiptChain",
    "DistributedReceiptConflict",
    "DistributedReceiptCorruption",
    "DistributedReceiptHead",
    "GENESIS_HASH",
    "ReceiptInclusion",
    "ReceiptIndexEntry",
]
