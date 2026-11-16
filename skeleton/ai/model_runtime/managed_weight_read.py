"""Noncreating managed read guard for runtime inspection and decoder custody."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .weight_shard_store import WeightShardStore, WeightShardStoreError
from .weight_store_disk_owner import WeightStoreDiskOwner


_CONTROL_NAMES = (
    ".weight-stage.lock", ".weight-stage-policy.json", ".weight-stage-intent.json",
    ".weight-stage-last.json", ".weight-stage-scrub.json",
)


@contextmanager
def managed_weight_read(store: WeightShardStore) -> Iterator[WeightStoreDiskOwner | None]:
    """Hold shared writer exclusion if this store has managed control records.

    Legacy unprovisioned stores retain independent content verification.
    Once managed, missing/corrupt control records or an active interrupted
    intent fail closed. Provisioning a legacy store requires operator-idle
    custody; this function cannot coordinate old unmodified processes.
    """
    if not isinstance(store, WeightShardStore):
        raise WeightShardStoreError("canonical weight store required")
    store.assert_layout()
    managed = any((store.root / name).exists() or (store.root / name).is_symlink()
                  for name in _CONTROL_NAMES)
    if not managed:
        yield None
        store.assert_layout()
        if any((store.root / name).exists() or (store.root / name).is_symlink()
               for name in _CONTROL_NAMES):
            raise WeightShardStoreError("managed store provisioning appeared during legacy inspection")
        return
    owner = WeightStoreDiskOwner.open_existing(store)
    with owner.read_guard():
        yield owner
