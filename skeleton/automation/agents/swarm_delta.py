"""Compact deterministic deltas between swarm snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SnapshotDelta:
    added_tasks: tuple[str, ...]
    removed_tasks: tuple[str, ...]
    changed_tasks: tuple[str, ...]
    added_workers: tuple[str, ...]
    removed_workers: tuple[str, ...]


def _index(items: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for item in items:
        if isinstance(item, Mapping) and "id" in item:
            result[str(item["id"])] = item
    return result


def diff_snapshots(before: Mapping[str, object], after: Mapping[str, object]) -> SnapshotDelta:
    before_tasks = _index(before.get("tasks"))
    after_tasks = _index(after.get("tasks"))
    before_workers = _index(before.get("workers"))
    after_workers = _index(after.get("workers"))

    before_task_ids = set(before_tasks)
    after_task_ids = set(after_tasks)
    common_tasks = before_task_ids & after_task_ids
    changed = sorted(task_id for task_id in common_tasks if before_tasks[task_id] != after_tasks[task_id])

    return SnapshotDelta(
        added_tasks=tuple(sorted(after_task_ids - before_task_ids)),
        removed_tasks=tuple(sorted(before_task_ids - after_task_ids)),
        changed_tasks=tuple(changed),
        added_workers=tuple(sorted(set(after_workers) - set(before_workers))),
        removed_workers=tuple(sorted(set(before_workers) - set(after_workers))),
    )

# Journal encoding for the existing recovery manager. Not a second durable
# store. A checkpoint is the commit granularity; intermediate transitions
# that were never checkpointed are intentionally not represented.
MAX_JOURNAL_RECORDS = 64
MAX_REPLAY_BYTES = 8 * 1024 * 1024


def _canonical(value: object) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    from hashlib import sha256
    return sha256(_canonical(value)).hexdigest()


def _strict_index(rows: object) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError("journal records must be lists")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("id")) is not str or not row["id"] or row["id"] in result:
            raise ValueError("invalid or duplicate journal record identity")
        result[row["id"]] = row
    return result


def _ownership(sidecar: dict) -> dict[str, str]:
    owners = {}
    for phase in ("active", "terminal"):
        rows = sidecar.get(phase)
        if not isinstance(rows, list):
            raise ValueError("missing journal tenant sidecar")
        for row in rows:
            if (not isinstance(row, (list, tuple)) or len(row) != 2
                    or any(type(v) is not str or not v for v in row) or row[0] in owners):
                raise ValueError("invalid journal tenant identity")
            task, tenant = row
            owners[task] = tenant
    return owners


def _patch(before: dict, after: dict) -> dict:
    return {
        "delete": sorted(set(before) - set(after)),
        "upsert": [after[key] for key in sorted(after)
                   if key not in before or _canonical(before[key]) != _canonical(after[key])],
    }


def _apply(before: dict, patch: object) -> dict:
    if not isinstance(patch, dict) or set(patch) != {"delete", "upsert"}:
        raise ValueError("invalid journal patch")
    deletes = patch["delete"]
    if not isinstance(deletes, list) or any(type(key) is not str for key in deletes):
        raise ValueError("invalid journal deletion")
    if deletes != sorted(set(deletes)) or any(key not in before for key in deletes):
        raise ValueError("invalid journal deletion identity")
    rows = _strict_index(patch["upsert"])
    if set(rows) & set(deletes):
        raise ValueError("overlapping journal patch")
    result = dict(before)
    for key in deletes:
        del result[key]
    result.update(rows)
    return result


def _partitions(tasks: dict, ownership: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for key, row in tasks.items():
        tenant = ownership.get(key)
        if tenant is None:
            raise ValueError("unowned task in verified journal")
        result.setdefault(tenant, {})[key] = row
    return result


def _indexed_sidecars(sidecars: object) -> dict[int, dict]:
    if not isinstance(sidecars, list) or len(sidecars) > MAX_JOURNAL_RECORDS:
        raise ValueError("invalid journal sidecar count")
    result = {}
    for row in sidecars:
        if (not isinstance(row, dict) or type(row.get("sequence")) is not int
                or row["sequence"] < 1 or row["sequence"] in result):
            raise ValueError("invalid journal sidecar sequence")
        result[row["sequence"]] = row
    return result


def encode_checkpoint_journal(records: list[dict], sidecars: list[dict]) -> list[dict]:
    """Encode deterministic partitioned state changes from retained checkpoints.

    The first record is a materialized replay anchor; replacing the anchor on
    retention-ring compaction keeps all remaining checkpoints reconstructible.
    Terminal identities remain in the existing verified tenant sidecars.
    The outer archive must be committed by the existing exclusive run writer.
    Hash chains detect accidental corruption, not a hostile writer with access
    to all bytes or rollback of the entire independently unpinned archive.
    """
    if not isinstance(records, list) or len(records) > MAX_JOURNAL_RECORDS:
        raise ValueError("journal record ceiling")
    owners_by_sequence = _indexed_sidecars(sidecars)
    if len(owners_by_sequence) != len(records):
        raise ValueError("journal requires aligned tenant history")
    if len(_canonical([records, sidecars])) > MAX_REPLAY_BYTES:
        raise ValueError("journal expanded replay exceeds bound")
    previous_tasks: dict = {}
    previous_workers: dict = {}
    previous_owners: dict = {}
    previous_hash = "0" * 64
    previous_sequence = 0
    result = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {"sequence", "created_at", "checksum", "state"}:
            raise ValueError("invalid source checkpoint record")
        sequence = record["sequence"]
        if type(sequence) is not int or sequence <= previous_sequence or sequence not in owners_by_sequence:
            raise ValueError("journal sequence disorder")
        state = record["state"]
        if (not isinstance(state, dict) or state.get("version") not in (2, 3)
                or not isinstance(state.get("config"), dict) or state["config"].get("fenced") is not True):
            raise ValueError("journal requires verified fenced checkpoints")
        owners = _ownership(owners_by_sequence[sequence])
        if any(owners.get(key) != tenant for key, tenant in previous_owners.items()):
            raise ValueError("verified journal owner identity removed or changed")
        tasks = _partitions(_strict_index(state.get("tasks")), owners)
        workers = _strict_index(state.get("workers"))
        changes = []
        for tenant in sorted(set(tasks) | set(previous_tasks)):
            patch = _patch(previous_tasks.get(tenant, {}), tasks.get(tenant, {}))
            if patch["delete"] or patch["upsert"]:
                changes.append({"tenant": tenant, **patch})
        body = {
            "sequence": sequence, "created_at": record["created_at"], "checksum": record["checksum"],
            "previous_sha256": previous_hash,
            "tenant_checksum": owners_by_sequence[sequence].get("checksum"),
            "header": {key: value for key, value in state.items() if key not in {"tasks", "workers"}},
            "task_partitions": changes, "workers": _patch(previous_workers, workers),
        }
        previous_hash = _digest(body)
        result.append({**body, "event_sha256": previous_hash})
        previous_tasks, previous_workers, previous_owners = tasks, workers, owners
        previous_sequence = sequence
    return result


def replay_checkpoint_journal(events: list[dict], sidecars: list[dict]) -> list[dict]:
    """Reconstruct each committed state and reject noncanonical or corrupted chains."""
    if not isinstance(events, list) or len(events) > MAX_JOURNAL_RECORDS:
        raise ValueError("journal record ceiling")
    if len(_canonical([events, sidecars])) > MAX_REPLAY_BYTES:
        raise ValueError("journal input exceeds bound")
    owners_by_sequence = _indexed_sidecars(sidecars)
    if len(owners_by_sequence) != len(events):
        raise ValueError("journal requires aligned tenant history")
    fields = {"sequence", "created_at", "checksum", "previous_sha256", "tenant_checksum",
              "header", "task_partitions", "workers", "event_sha256"}
    partitions: dict[str, dict] = {}
    workers: dict = {}
    previous = "0" * 64
    last_sequence = 0
    total_bytes = 0
    records = []
    for event in events:
        if not isinstance(event, dict) or set(event) != fields:
            raise ValueError("invalid journal event fields")
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        sequence = body["sequence"]
        if (type(sequence) is not int or sequence <= last_sequence or sequence not in owners_by_sequence
                or body["previous_sha256"] != previous or _digest(body) != event["event_sha256"]
                or body["tenant_checksum"] != owners_by_sequence[sequence].get("checksum")):
            raise ValueError("journal chain or tenant seal mismatch")
        header = body["header"]
        if not isinstance(header, dict) or "tasks" in header or "workers" in header:
            raise ValueError("invalid journal header")
        changes = body["task_partitions"]
        if not isinstance(changes, list):
            raise ValueError("invalid task partition changes")
        seen = set()
        for row in changes:
            if not isinstance(row, dict) or set(row) != {"tenant", "delete", "upsert"}:
                raise ValueError("invalid tenant patch")
            tenant = row["tenant"]
            if type(tenant) is not str or not tenant or tenant in seen:
                raise ValueError("duplicate or invalid journal partition")
            seen.add(tenant)
            updated = _apply(partitions.get(tenant, {}), {"delete": row["delete"], "upsert": row["upsert"]})
            if updated:
                partitions[tenant] = updated
            else:
                partitions.pop(tenant, None)
        owners = _ownership(owners_by_sequence[sequence])
        tasks = {}
        for tenant, entries in partitions.items():
            for key, row in entries.items():
                if key in tasks or owners.get(key) != tenant:
                    raise ValueError("cross-tenant journal replay")
                tasks[key] = row
        workers = _apply(workers, body["workers"])
        state = {**header, "tasks": [tasks[key] for key in sorted(tasks)],
                 "workers": [workers[key] for key in sorted(workers)]}
        # CheckpointStore normalizes these arrays and hashes canonical JSON.
        if _digest(state) != body["checksum"]:
            raise ValueError("journal reconstructed checkpoint checksum mismatch")
        record = {"sequence": sequence, "created_at": body["created_at"],
                  "checksum": body["checksum"], "state": state}
        total_bytes += len(_canonical(record))
        if total_bytes > MAX_REPLAY_BYTES:
            raise ValueError("journal expanded replay exceeds bound")
        records.append(record)
        previous = event["event_sha256"]
        last_sequence = sequence
    # Canonical re-encoding proves exact partition identity, order, no
    # hidden redundant writes, and retention of previous tenant tombstones.
    if _canonical(encode_checkpoint_journal(records, sidecars)) != _canonical(events):
        raise ValueError("noncanonical journal changes")
    return records
