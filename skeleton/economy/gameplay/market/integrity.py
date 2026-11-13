"""Market integrity checks.

Three families, each recorded as an *incident* with a stable ``kind``:

``wash``
    Both sides of a fill belong to the same owner or to one *linked circle*.
    Circles come from declared links (alts, shared device, guild bank) via
    :class:`AccountLinks` and from detected circular trading: when an item's
    recent prints form a cycle (A->B->C->A) inside ``cycle_ticks``, every
    owner on the cycle is linked, so later fills between them are refused.

``spoof`` / ``out_of_band``
    :class:`ManipulationMonitor` keeps an EMA reference price per item and
    refuses prints outside ``±band_bps`` of it. It also tracks, per owner,
    how much order notional was cancelled within ``spoof_ticks`` of being
    placed while mostly unfilled; owners whose fast-cancel ratio exceeds the
    threshold are restricted from placing orders for ``penalty_ticks``.

``duplicate``
    :class:`SerialRegistry` gives serialized items unique IDs. A listing may
    only escrow serials that the seller holds and that are not already
    escrowed or held elsewhere; :meth:`SerialRegistry.audit` checks serial
    counts never exceed inventory counts (item-ID conservation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.economy.gameplay.market.errors import IntegrityViolation, MarketError
from skeleton.simulation.economy.sim import BPS, _req_id, _req_int

WASH = "wash"
CIRCULAR = "circular"
SPOOF = "spoof"
OUT_OF_BAND = "out_of_band"
DUPLICATE = "duplicate"
KINDS = (WASH, CIRCULAR, SPOOF, OUT_OF_BAND, DUPLICATE)


@dataclass
class IncidentLog:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, tick: int, kind: str, **ctx: Any) -> dict[str, Any]:
        if kind not in KINDS:
            raise MarketError(f"unknown incident kind {kind!r}")
        row = {"tick": tick, "kind": kind, **{k: ctx[k] for k in sorted(ctx)}}
        self.rows.append(row)
        return row

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows if r["kind"] == kind]

    def counts(self) -> dict[str, int]:
        out = {k: 0 for k in KINDS}
        for r in self.rows:
            out[r["kind"]] += 1
        return out


class AccountLinks:
    """Union-find over owners; deterministic roots (lexicographically smallest)."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._reasons: list[tuple[str, str, str]] = []

    def _find(self, a: str) -> str:
        parent = self._parent.setdefault(a, a)
        if parent == a:
            return a
        root = self._find(parent)
        self._parent[a] = root
        return root

    def link(self, a: str, b: str, reason: str = "declared") -> None:
        _req_id(a, "owner")
        _req_id(b, "owner")
        ra, rb = self._find(a), self._find(b)
        self._reasons.append((min(a, b), max(a, b), reason))
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        self._parent[hi] = lo

    def linked(self, a: str, b: str) -> bool:
        return a == b or self._find(a) == self._find(b)

    def circle(self, a: str) -> list[str]:
        root = self._find(a)
        return sorted(o for o in list(self._parent) if self._find(o) == root)

    def to_state(self) -> list[list[str]]:
        return [list(r) for r in self._reasons]

    @classmethod
    def from_state(cls, rows: Iterable[Iterable[str]]) -> "AccountLinks":
        links = cls()
        for a, b, reason in rows:
            links.link(a, b, reason)
        return links


@dataclass
class WashTradeDetector:
    links: AccountLinks = field(default_factory=AccountLinks)
    cycle_ticks: int = 500
    max_cycle: int = 4
    _prints: dict[str, list[tuple[int, str, str]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _req_int(self.cycle_ticks, "cycle_ticks", minimum=1)
        _req_int(self.max_cycle, "max_cycle", minimum=2)

    def is_wash(self, seller: str, buyer: str) -> bool:
        return self.links.linked(seller, buyer)

    def _path(
        self, edges: list[tuple[str, str]], start: str, goal: str
    ) -> list[str] | None:
        """Shortest item-flow path start -> goal with at most ``max_cycle - 1`` hops (BFS)."""
        adj: dict[str, list[str]] = {}
        for s, b in edges:
            adj.setdefault(s, [])
            if b not in adj[s]:
                adj[s].append(b)
        frontier = [[start]]
        seen = {start}
        for _ in range(self.max_cycle - 1):
            nxt: list[list[str]] = []
            for path in frontier:
                for n in sorted(adj.get(path[-1], [])):
                    if n == goal:
                        return path + [n]
                    if n not in seen:
                        seen.add(n)
                        nxt.append(path + [n])
            frontier = nxt
        return None

    def observe(
        self, tick: int, item_id: str, seller: str, buyer: str
    ) -> list[str] | None:
        """Record a print; return the cycle's owners if it closes one."""
        rows = [
            p for p in self._prints.get(item_id, []) if tick - p[0] <= self.cycle_ticks
        ]
        cycle = self._path([(s, b) for _, s, b in rows], buyer, seller)
        rows.append((tick, seller, buyer))
        self._prints[item_id] = rows
        if cycle is None:
            return None
        owners = sorted(set(cycle))
        for other in owners[1:]:
            self.links.link(owners[0], other, f"circular:{item_id}")
        return owners

    def to_state(self) -> dict[str, Any]:
        return {
            "cycle_ticks": self.cycle_ticks,
            "max_cycle": self.max_cycle,
            "links": self.links.to_state(),
            "prints": {
                k: [list(p) for p in v] for k, v in sorted(self._prints.items())
            },
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "WashTradeDetector":
        det = cls(
            AccountLinks.from_state(state["links"]),
            int(state["cycle_ticks"]),
            int(state["max_cycle"]),
        )
        det._prints = {
            k: [(int(t), str(s), str(b)) for t, s, b in v]
            for k, v in state["prints"].items()
        }
        return det


@dataclass
class _OwnerFlow:
    placed: list[tuple[int, int]] = field(default_factory=list)
    fast_cancelled: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class ManipulationMonitor:
    band_bps: int = 3_000
    ema_bps: int = 2_000
    spoof_ticks: int = 10
    spoof_window: int = 200
    spoof_ratio_bps: int = 8_000
    spoof_min_orders: int = 3
    spoof_fill_bps: int = 1_000
    penalty_ticks: int = 300
    _reference: dict[str, int] = field(default_factory=dict)
    _flows: dict[str, _OwnerFlow] = field(default_factory=dict)
    _restricted: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "band_bps",
            "ema_bps",
            "spoof_ticks",
            "spoof_window",
            "spoof_ratio_bps",
            "spoof_min_orders",
            "penalty_ticks",
        ):
            _req_int(getattr(self, name), name, minimum=1)
        _req_int(self.spoof_fill_bps, "spoof_fill_bps")
        if (
            self.ema_bps > BPS
            or self.spoof_ratio_bps > BPS
            or self.spoof_fill_bps > BPS
        ):
            raise MarketError("bps parameter above 100%")

    # -- reference prices / out-of-band prints ------------------------------
    def seed(self, item_id: str, unit_price: int) -> None:
        self._reference.setdefault(
            item_id, _req_int(unit_price, "unit_price", minimum=1)
        )

    def set_reference(self, item_id: str, unit_price: int) -> None:
        self._reference[item_id] = _req_int(unit_price, "unit_price", minimum=1)

    def reference(self, item_id: str) -> int | None:
        return self._reference.get(item_id)

    def band(self, item_id: str) -> tuple[int, int] | None:
        ref = self._reference.get(item_id)
        if ref is None:
            return None
        width = ref * self.band_bps // BPS
        return max(1, ref - width), ref + width

    def in_band(self, item_id: str, unit_price: int) -> bool:
        bounds = self.band(item_id)
        return bounds is None or bounds[0] <= unit_price <= bounds[1]

    def on_print(self, item_id: str, unit_price: int) -> int:
        ref = self._reference.get(item_id)
        new = (
            unit_price
            if ref is None
            else ref + (unit_price - ref) * self.ema_bps // BPS
        )
        self._reference[item_id] = new
        return new

    # -- spoofing ---------------------------------------------------------------
    def restricted_until(self, owner: str) -> int | None:
        return self._restricted.get(owner)

    def is_restricted(self, owner: str, tick: int) -> bool:
        until = self._restricted.get(owner)
        return until is not None and tick < until

    def _flow(self, owner: str, tick: int) -> _OwnerFlow:
        flow = self._flows.setdefault(owner, _OwnerFlow())
        flow.placed = [p for p in flow.placed if tick - p[0] < self.spoof_window]
        flow.fast_cancelled = [
            p for p in flow.fast_cancelled if tick - p[0] < self.spoof_window
        ]
        return flow

    def on_place(self, owner: str, tick: int, notional: int) -> None:
        self._flow(owner, tick).placed.append((tick, notional))

    def on_cancel(
        self,
        owner: str,
        tick: int,
        placed_tick: int,
        qty: int,
        remaining: int,
        notional: int,
    ) -> bool:
        """Record a cancel; returns True when it tips ``owner`` into spoofing."""
        flow = self._flow(owner, tick)
        filled_bps = (qty - remaining) * BPS // qty
        if tick - placed_tick <= self.spoof_ticks and filled_bps <= self.spoof_fill_bps:
            flow.fast_cancelled.append((tick, notional))
        placed = sum(n for _, n in flow.placed)
        fast = sum(n for _, n in flow.fast_cancelled)
        if (
            len(flow.fast_cancelled) >= self.spoof_min_orders
            and placed
            and fast * BPS // placed >= self.spoof_ratio_bps
        ):
            self._restricted[owner] = tick + self.penalty_ticks
            flow.fast_cancelled.clear()
            flow.placed.clear()
            return True
        return False

    def to_state(self) -> dict[str, Any]:
        return {
            "params": {
                k: getattr(self, k)
                for k in (
                    "band_bps",
                    "ema_bps",
                    "spoof_ticks",
                    "spoof_window",
                    "spoof_ratio_bps",
                    "spoof_min_orders",
                    "spoof_fill_bps",
                    "penalty_ticks",
                )
            },
            "reference": dict(sorted(self._reference.items())),
            "flows": {
                o: {
                    "placed": [list(p) for p in f.placed],
                    "fast": [list(p) for p in f.fast_cancelled],
                }
                for o, f in sorted(self._flows.items())
            },
            "restricted": dict(sorted(self._restricted.items())),
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "ManipulationMonitor":
        mon = cls(**{k: int(v) for k, v in state["params"].items()})
        mon._reference = {k: int(v) for k, v in state["reference"].items()}
        mon._flows = {
            o: _OwnerFlow(
                [(int(t), int(n)) for t, n in f["placed"]],
                [(int(t), int(n)) for t, n in f["fast"]],
            )
            for o, f in state["flows"].items()
        }
        mon._restricted = {k: int(v) for k, v in state["restricted"].items()}
        return mon


class SerialRegistry:
    """Unique IDs for serialized items; enforces item-ID conservation."""

    def __init__(self, serialized: Iterable[str] = ()) -> None:
        self.serialized = frozenset(serialized)
        self._holder: dict[str, tuple[str, str]] = {}

    def is_serialized(self, item_id: str) -> bool:
        return item_id in self.serialized

    def register(self, item_id: str, holder: str, serial: str) -> None:
        """Bind a freshly minted unit's serial to its holder."""
        if item_id not in self.serialized:
            raise MarketError("item is not serialized")
        _req_id(serial, "serial")
        if serial in self._holder:
            raise IntegrityViolation("serial already exists")
        self._holder[serial] = (item_id, holder)

    def retire(self, serial: str) -> None:
        """Remove a serial whose unit was consumed or sold to a vendor."""
        if self._holder.pop(serial, None) is None:
            raise MarketError("no such serial")

    def holder(self, serial: str) -> tuple[str, str] | None:
        return self._holder.get(serial)

    def serials_of(self, holder: str, item_id: str) -> list[str]:
        return sorted(
            s for s, (i, h) in self._holder.items() if h == holder and i == item_id
        )

    def problem(
        self, item_id: str, holder: str, serials: Iterable[str], qty: int
    ) -> str | None:
        """Why ``serials`` cannot be escrowed by ``holder``, or ``None``."""
        listed = list(serials)
        if item_id not in self.serialized:
            return "serials given for non-serialized item" if listed else None
        if len(listed) != qty:
            return "serial count does not match quantity"
        if len(set(listed)) != len(listed):
            return "serial repeated in one listing"
        for serial in listed:
            rec = self._holder.get(serial)
            if rec is None:
                return f"unknown serial {serial}"
            if rec[0] != item_id:
                return f"serial {serial} belongs to another item"
            if rec[1] != holder:
                return f"serial {serial} is held by someone else"
        return None

    def move(self, serials: Iterable[str], to: str) -> None:
        for serial in serials:
            item_id, _ = self._holder[serial]
            self._holder[serial] = (item_id, to)

    def audit(self, counts: Mapping[tuple[str, str], int]) -> dict[str, Any]:
        """``counts[(holder, item)]`` is inventory; serial counts must equal it."""
        per: dict[tuple[str, str], int] = {}
        for item_id, holder in self._holder.values():
            per[(holder, item_id)] = per.get((holder, item_id), 0) + 1
        problems = []
        for key in sorted(set(per) | {k for k in counts if k[1] in self.serialized}):
            if per.get(key, 0) != counts.get(key, 0):
                problems.append(
                    {
                        "holder": key[0],
                        "item": key[1],
                        "serials": per.get(key, 0),
                        "held": counts.get(key, 0),
                    }
                )
        return {"ok": not problems, "problems": problems}

    def to_state(self) -> dict[str, Any]:
        return {
            "serialized": sorted(self.serialized),
            "holders": {s: list(v) for s, v in sorted(self._holder.items())},
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "SerialRegistry":
        reg = cls(state["serialized"])
        reg._holder = {s: (str(v[0]), str(v[1])) for s, v in state["holders"].items()}
        return reg


__all__ = [
    "CIRCULAR",
    "DUPLICATE",
    "KINDS",
    "OUT_OF_BAND",
    "SPOOF",
    "WASH",
    "AccountLinks",
    "IncidentLog",
    "ManipulationMonitor",
    "SerialRegistry",
    "WashTradeDetector",
]
