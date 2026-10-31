"""B062 - server-authoritative replication with delta compression and a budget.

* Server owns state (``dict[entity_id, dict[field, int]]``); clients never write it.
* Each client acks snapshot ticks; deltas are encoded against the newest acked
  baseline, so losing any packet only costs bandwidth, never correctness.
* :class:`BandwidthBudget` caps bytes per client per tick. Entities are ordered
  by accumulated priority (base priority x starvation age, relevancy-gated), so
  starved entities rise until they fit.
* :class:`LossyLink` is a seeded loss/reorder/duplicate simulator.
"""
from __future__ import annotations

import random
import struct
from dataclasses import dataclass, field
from typing import Callable, Optional

State = dict[int, dict[str, int]]
_HDR = struct.Struct(">IIH")       # tick, baseline tick, entity count
_ENT = struct.Struct(">IBB")       # entity id, op (0=upsert,1=remove), field count
_FLD = struct.Struct(">Bq")        # field index, value
FIELDS: tuple[str, ...] = ("x", "y", "z", "vx", "vy", "hp", "state", "owner")
_IDX = {n: i for i, n in enumerate(FIELDS)}


@dataclass(frozen=True)
class Snapshot:
    tick: int
    baseline: int
    entities: dict[int, Optional[dict[str, int]]]  # None => removed


def encode_delta(tick: int, baseline_tick: int, baseline: State, current: State,
                 order: Optional[list[int]] = None, budget: Optional[int] = None) -> tuple[bytes, list[int]]:
    """Encode changed fields since ``baseline``. Returns (bytes, entity ids included).

    ``order`` lets the caller pass priority order; ``budget`` caps total bytes.
    """
    changed: dict[int, bytes] = {}
    for eid in sorted(set(baseline) | set(current)):
        cur, base = current.get(eid), baseline.get(eid)
        if cur is None:
            changed[eid] = _ENT.pack(eid, 1, 0)
            continue
        diff = [(k, v) for k, v in sorted(cur.items(), key=lambda kv: _IDX[kv[0]]) if base is None or base.get(k) != v]
        if diff:
            changed[eid] = _ENT.pack(eid, 0, len(diff)) + b"".join(_FLD.pack(_IDX[k], v) for k, v in diff)
    ids = [e for e in (order or sorted(changed)) if e in changed]
    ids += [e for e in sorted(changed) if e not in ids]
    out, used, size = [], [], _HDR.size
    for eid in ids:
        blob = changed[eid]
        if budget is not None and size + len(blob) > budget:
            continue
        out.append(blob)
        used.append(eid)
        size += len(blob)
    return _HDR.pack(tick, baseline_tick, len(out)) + b"".join(out), used


def decode_delta(data: bytes) -> Snapshot:
    try:
        tick, base, n = _HDR.unpack_from(data)
        off, ents = _HDR.size, {}
        for _ in range(n):
            eid, op, nf = _ENT.unpack_from(data, off)
            off += _ENT.size
            if op == 1:
                ents[eid] = None
                continue
            if op != 0:
                raise ValueError("bad op")
            f = {}
            for _ in range(nf):
                idx, val = _FLD.unpack_from(data, off)
                off += _FLD.size
                f[FIELDS[idx]] = val
            ents[eid] = f
        if off != len(data):
            raise ValueError("trailing bytes")
    except (struct.error, IndexError) as exc:
        raise ValueError("malformed snapshot") from exc
    return Snapshot(tick, base, ents)


@dataclass
class BandwidthBudget:
    bytes_per_tick: int = 1024

    def __post_init__(self) -> None:
        if self.bytes_per_tick < _HDR.size + _ENT.size + _FLD.size:
            raise ValueError("budget too small for one field")


@dataclass
class _ClientView:
    acked_tick: int = 0
    acked_state: State = field(default_factory=dict)
    sent: dict[int, State] = field(default_factory=dict)  # tick -> state the client will have if acked
    age: dict[int, int] = field(default_factory=dict)


class ServerReplicator:
    def __init__(self, budget: BandwidthBudget = BandwidthBudget(),
                 priority: Callable[[int, dict[str, int]], float] = lambda e, s: 1.0,
                 relevant: Callable[[str, int, dict[str, int]], bool] = lambda c, e, s: True,
                 history: int = 64) -> None:
        self.state: State = {}
        self.tick = 1  # tick 0 is the implicit empty baseline
        self.budget = budget
        self.priority = priority
        self.relevant = relevant
        self.history = history
        self.clients: dict[str, _ClientView] = {}
        self.bytes_sent: list[int] = []

    def add_client(self, cid: str) -> None:
        self.clients[cid] = _ClientView()

    def set(self, eid: int, **fields: int) -> None:
        for k in fields:
            if k not in _IDX:
                raise KeyError(k)
        self.state.setdefault(eid, {}).update({k: int(v) for k, v in fields.items()})

    def remove(self, eid: int) -> None:
        self.state.pop(eid, None)

    def step(self) -> None:
        self.tick += 1

    def snapshot_for(self, cid: str) -> bytes:
        view = self.clients[cid]
        target = {e: dict(s) for e, s in self.state.items() if self.relevant(cid, e, s)}
        for e in list(view.age):
            if e not in target and e not in view.acked_state:
                view.age.pop(e)
        for e in set(target) | set(view.acked_state):
            view.age[e] = view.age.get(e, 0) + 1
        order = sorted(view.age, key=lambda e: (-(self.priority(e, target.get(e, {})) * view.age[e]), e))
        data, used = encode_delta(self.tick, view.acked_tick, view.acked_state, target, order,
                                  self.budget.bytes_per_tick)
        resulting = {e: dict(s) for e, s in view.acked_state.items()}
        for e in used:
            view.age[e] = 0
            if e in target:
                resulting[e] = dict(target[e])
            else:
                resulting.pop(e, None)
        view.sent[self.tick] = resulting
        for t in [t for t in view.sent if t <= self.tick - self.history]:
            view.sent.pop(t)
        self.bytes_sent.append(len(data))
        return data

    def ack(self, cid: str, tick: int) -> None:
        view = self.clients[cid]
        if tick > view.acked_tick and tick in view.sent:
            view.acked_tick, view.acked_state = tick, view.sent[tick]
            for t in [t for t in view.sent if t < tick]:
                view.sent.pop(t)


class ClientReplica:
    """Applies snapshots; keeps a baseline per received tick so out-of-order deltas resolve."""

    def __init__(self, history: int = 64) -> None:
        self.state: State = {}
        self.tick = 0
        self.history = history
        self._baselines: dict[int, State] = {0: {}}
        self.rejected = 0

    def receive(self, data: bytes) -> Optional[int]:
        try:
            snap = decode_delta(data)
        except ValueError:
            self.rejected += 1
            return None
        if snap.tick <= self.tick or snap.baseline not in self._baselines:
            self.rejected += 1  # stale or baseline unknown: drop, server will resend
            return None
        st = {e: dict(f) for e, f in self._baselines[snap.baseline].items()}
        for e, f in snap.entities.items():
            if f is None:
                st.pop(e, None)
            else:
                st.setdefault(e, {}).update(f)
        self.state, self.tick = st, snap.tick
        self._baselines[snap.tick] = {e: dict(f) for e, f in st.items()}
        for t in [t for t in self._baselines if t < snap.tick - self.history]:
            self._baselines.pop(t)
        return snap.tick  # caller sends this as the ack


class LossyLink:
    """Seeded unreliable link: drop, duplicate and reorder (bounded delay in ticks)."""

    def __init__(self, seed: int, loss: float = 0.0, duplicate: float = 0.0, max_delay: int = 0) -> None:
        self.rng = random.Random(seed)
        self.loss, self.duplicate, self.max_delay = loss, duplicate, max_delay
        self.now = 0
        self._q: list[tuple[int, int, bytes]] = []
        self._n = 0

    def send(self, data: bytes) -> None:
        if self.rng.random() < self.loss:
            return
        copies = 2 if self.rng.random() < self.duplicate else 1
        for _ in range(copies):
            self._n += 1
            self._q.append((self.now + self.rng.randint(0, self.max_delay), self._n, data))

    def advance(self) -> list[bytes]:
        self.now += 1
        due = sorted((x for x in self._q if x[0] <= self.now), key=lambda x: (x[0], self.rng.random()))
        self._q = [x for x in self._q if x[0] > self.now]
        return [d for _, _, d in due]
