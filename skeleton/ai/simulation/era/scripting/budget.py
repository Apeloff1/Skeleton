"""Pacing and encounter budgets for era data (STU-ERAS slice 5).

A *budget* is a small, declarative set of limits a level designer (or a later
forge/eras pipeline) can apply to a validated :class:`EraSpec` without
rendering or simulating anything:

* hard caps (``error``): room count, depth, boss count (min/max), per-kind
  room caps, and the total encounter cost of the era;
* pacing heuristics (``warning``): hop span from ``start``, lock density,
  distance from any room back to a rest room, depth jumps across one exit,
  and the encounter cost along the shortest route to each boss.

Encounter cost is a per-kind integer weight (see :data:`DEFAULT_COSTS`).
Everything is integer arithmetic (lock density is in per-mille) so reports
serialize to byte-identical JSON on every run and platform. Pure,
deterministic, stdlib-only, no network, no forge writes; inputs are never
mutated.

Campaign rollups (:func:`evaluate_campaign`) sum per-era metrics in
``(order, id)`` order, apply campaign-wide caps, and warn when an era is
cheaper than the one before it (``difficulty-regression``).

CLI::

    python -m skeleton.simulation.era.scripting.budget FILE [FILE ...]
        [--budget BUDGET.json] [--campaign]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from skeleton.simulation.era.scripting.analysis import (
    ERROR,
    WARNING,
    Finding,
    distances,
    shortest_path,
)
from skeleton.simulation.era.scripting.canonical import digest
from skeleton.simulation.era.scripting.loader import MAX_BYTES, load_era_json
from skeleton.simulation.era.scripting.schema import ROOM_KINDS, EraSpec, SchemaError

BUDGET_VERSION = "stu-eras-budget/1"
REST_KINDS = ("hub", "safe")
DEFAULT_COSTS: dict[str, int] = {
    "hub": 0,
    "corridor": 1,
    "chamber": 1,
    "arena": 3,
    "safe": 0,
    "boss": 5,
    "secret": 1,
}
_INT_LIMIT = 1_000_000

_ERA_INT_FIELDS: dict[str, tuple[int, int]] = {
    # name: (lo, hi)
    "max_rooms": (1, 4096),
    "max_depth": (0, 255),
    "max_hops": (0, 4096),
    "min_bosses": (0, 4096),
    "max_bosses": (0, 4096),
    "max_locked_permille": (0, 1000),
    "max_rest_gap": (0, 4096),
    "max_depth_step": (0, 255),
    "max_cost": (0, _INT_LIMIT),
    "max_path_cost": (0, _INT_LIMIT),
}


def _int(value: Any, path: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("bad-int", path, f"expected int, got {type(value).__name__}")
    if not lo <= value <= hi:
        raise SchemaError("out-of-range", path, f"expected {lo}..{hi}, got {value}")
    return value


def _kind_map(
    value: Any, path: str, *, lo: int, hi: int
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, dict):
        raise SchemaError(
            "bad-type", path, f"expected object, got {type(value).__name__}"
        )
    out: dict[str, int] = {}
    for kind in sorted(value):
        if kind not in ROOM_KINDS:
            raise SchemaError(
                "bad-room-kind", f"{path}.{kind}", f"one of {list(ROOM_KINDS)}"
            )
        out[kind] = _int(value[kind], f"{path}.{kind}", lo, hi)
    return tuple(sorted(out.items()))


def _only(data: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    extra = sorted(set(data) - set(allowed))
    if extra:
        raise SchemaError(
            "unknown-field", f"{path}.{extra[0]}", f"allowed: {sorted(allowed)}"
        )


@dataclass(frozen=True)
class EraBudget:
    """Per-era limits. Defaults are permissive enough for the shipped eras."""

    max_rooms: int = 64
    max_depth: int = 16
    max_hops: int = 24
    min_bosses: int = 0
    max_bosses: int = 1
    max_locked_permille: int = 500
    max_rest_gap: int = 6
    max_depth_step: int = 1
    max_cost: int = 120
    max_path_cost: int = 40
    kind_caps: tuple[tuple[str, int], ...] = ()
    costs: tuple[tuple[str, int], ...] = tuple(sorted(DEFAULT_COSTS.items()))

    def __post_init__(self) -> None:
        for name, (lo, hi) in _ERA_INT_FIELDS.items():
            _int(getattr(self, name), f"budget.{name}", lo, hi)
        if self.min_bosses > self.max_bosses:
            raise SchemaError(
                "bad-budget", "budget.min_bosses", "min_bosses must be <= max_bosses"
            )
        object.__setattr__(
            self,
            "kind_caps",
            _kind_map(dict(self.kind_caps), "budget.kind_caps", lo=0, hi=4096),
        )
        costs = dict(DEFAULT_COSTS)
        costs.update(dict(_kind_map(dict(self.costs), "budget.costs", lo=0, hi=1000)))
        object.__setattr__(self, "costs", tuple(sorted(costs.items())))

    @classmethod
    def from_dict(cls, data: Any, path: str = "budget") -> "EraBudget":
        if not isinstance(data, dict):
            raise SchemaError(
                "bad-type", path, f"expected object, got {type(data).__name__}"
            )
        _only(data, set(_ERA_INT_FIELDS) | {"kind_caps", "costs"}, path)
        kwargs: dict[str, Any] = {}
        for name, (lo, hi) in _ERA_INT_FIELDS.items():
            if name in data:
                kwargs[name] = _int(data[name], f"{path}.{name}", lo, hi)
        if "kind_caps" in data:
            kwargs["kind_caps"] = _kind_map(
                data["kind_caps"], f"{path}.kind_caps", lo=0, hi=4096
            )
        if "costs" in data:
            kwargs["costs"] = _kind_map(data["costs"], f"{path}.costs", lo=0, hi=1000)
        return cls(**kwargs)

    def cost_of(self, kind: str) -> int:
        return dict(self.costs)[kind]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            name: getattr(self, name) for name in sorted(_ERA_INT_FIELDS)
        }
        out["kind_caps"] = dict(self.kind_caps)
        out["costs"] = dict(self.costs)
        return out


@dataclass(frozen=True)
class CampaignBudget:
    """Campaign-wide caps on top of a shared :class:`EraBudget`."""

    era: EraBudget = field(default_factory=EraBudget)
    max_total_rooms: int = 1024
    max_total_cost: int = 2000
    rising_cost: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.era, EraBudget):
            raise SchemaError("bad-type", "budget.era", "expected EraBudget")
        _int(self.max_total_rooms, "budget.max_total_rooms", 1, _INT_LIMIT)
        _int(self.max_total_cost, "budget.max_total_cost", 0, _INT_LIMIT)
        if not isinstance(self.rising_cost, bool):
            raise SchemaError("bad-bool", "budget.rising_cost", "expected bool")

    @classmethod
    def from_dict(cls, data: Any, path: str = "budget") -> "CampaignBudget":
        """Accepts ``{"version", "era", "campaign"}``; every section optional."""
        if not isinstance(data, dict):
            raise SchemaError(
                "bad-type", path, f"expected object, got {type(data).__name__}"
            )
        _only(data, {"version", "era", "campaign"}, path)
        version = data.get("version", BUDGET_VERSION)
        if version != BUDGET_VERSION:
            raise SchemaError(
                "bad-schema", f"{path}.version", f"expected {BUDGET_VERSION!r}"
            )
        era = EraBudget.from_dict(data.get("era", {}), f"{path}.era")
        camp = data.get("campaign", {})
        if not isinstance(camp, dict):
            raise SchemaError("bad-type", f"{path}.campaign", "expected object")
        _only(
            camp,
            {"max_total_rooms", "max_total_cost", "rising_cost"},
            f"{path}.campaign",
        )
        kwargs: dict[str, Any] = {}
        if "max_total_rooms" in camp:
            kwargs["max_total_rooms"] = _int(
                camp["max_total_rooms"],
                f"{path}.campaign.max_total_rooms",
                1,
                _INT_LIMIT,
            )
        if "max_total_cost" in camp:
            kwargs["max_total_cost"] = _int(
                camp["max_total_cost"], f"{path}.campaign.max_total_cost", 0, _INT_LIMIT
            )
        if "rising_cost" in camp:
            if not isinstance(camp["rising_cost"], bool):
                raise SchemaError(
                    "bad-bool", f"{path}.campaign.rising_cost", "expected bool"
                )
            kwargs["rising_cost"] = camp["rising_cost"]
        return cls(era=era, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": BUDGET_VERSION,
            "era": self.era.to_dict(),
            "campaign": {
                "max_total_rooms": self.max_total_rooms,
                "max_total_cost": self.max_total_cost,
                "rising_cost": self.rising_cost,
            },
        }


DEFAULT_BUDGET = EraBudget()
DEFAULT_CAMPAIGN_BUDGET = CampaignBudget()


def _require_era(era: Any) -> EraSpec:
    if not isinstance(era, EraSpec):
        raise SchemaError(
            "bad-type", "era", f"expected EraSpec, got {type(era).__name__}"
        )
    return era


def rest_gaps(era: EraSpec) -> dict[str, int]:
    """Hops from each room to the nearest rest room (``hub``/``safe`` or start).

    Multi-source BFS over reversed exits (locked exits count: a key is a
    pacing gate, not a wall). Rooms that can never reach a rest room are
    absent from the result.
    """
    era = _require_era(era)
    incoming: dict[str, list[str]] = {r.id: [] for r in era.rooms}
    for room in era.rooms:
        for ex in room.exits:
            incoming[ex.target].append(room.id)
    sources = sorted({era.start} | {r.id for r in era.rooms if r.kind in REST_KINDS})
    gap = {rid: 0 for rid in sources}
    queue = deque(sources)
    while queue:
        cur = queue.popleft()
        for src in sorted(incoming[cur]):
            if src not in gap:
                gap[src] = gap[cur] + 1
                queue.append(src)
    return gap


def measure(era: EraSpec, budget: EraBudget = DEFAULT_BUDGET) -> dict[str, Any]:
    """Stable, JSON-ready pacing metrics for one era under ``budget`` costs."""
    era = _require_era(era)
    costs = dict(budget.costs)
    dist = distances(era)
    gaps = rest_gaps(era)
    reach = set(dist)
    exits = [ex for r in era.rooms for ex in r.exits]
    locked = sum(1 for ex in exits if ex.locked)
    bosses = sorted(r.id for r in era.rooms if r.kind == "boss")
    path_cost: dict[str, int] = {}
    for boss in bosses:
        path = shortest_path(era, era.start, boss)
        if path:
            path_cost[boss] = sum(costs[era.room(rid).kind] for rid in path[1:])
    step = 0
    for room in era.rooms:
        for ex in room.exits:
            step = max(step, era.room(ex.target).depth - room.depth)
    reach_gaps = [gaps[rid] for rid in reach if rid in gaps]
    return {
        "rooms": len(era.rooms),
        "kinds": {
            k: sum(1 for r in era.rooms if r.kind == k)
            for k in sorted({r.kind for r in era.rooms})
        },
        "max_depth": max(r.depth for r in era.rooms),
        "max_hops": max(dist.values()),
        "bosses": len(bosses),
        "exits": len(exits),
        "locked_exits": locked,
        "locked_permille": (locked * 1000) // len(exits) if exits else 0,
        "max_rest_gap": max(reach_gaps) if reach_gaps else 0,
        "stranded": sorted(rid for rid in reach if rid not in gaps),
        "max_depth_step": step,
        "cost": sum(costs[r.kind] for r in era.rooms),
        "boss_path_cost": dict(sorted(path_cost.items())),
    }


def check_budget(
    era: EraSpec,
    budget: EraBudget = DEFAULT_BUDGET,
    *,
    metrics: Mapping[str, Any] | None = None,
) -> tuple[Finding, ...]:
    """Budget findings for one era, sorted ``(path, code)``."""
    era = _require_era(era)
    if not isinstance(budget, EraBudget):
        raise SchemaError("bad-type", "budget", "expected EraBudget")
    m = dict(metrics) if metrics is not None else measure(era, budget)
    base = f"era.{era.id}"
    out: list[Finding] = []

    def over(code: str, path: str, got: int, cap: int, severity: str) -> None:
        if got > cap:
            out.append(Finding(code, path, f"{got} > {cap}", severity))

    over("budget-rooms", f"{base}.rooms", m["rooms"], budget.max_rooms, ERROR)
    over("budget-depth", f"{base}.depth", m["max_depth"], budget.max_depth, ERROR)
    over("budget-bosses", f"{base}.bosses", m["bosses"], budget.max_bosses, ERROR)
    if m["bosses"] < budget.min_bosses:
        out.append(
            Finding(
                "budget-min-bosses",
                f"{base}.bosses",
                f"{m['bosses']} < {budget.min_bosses}",
            )
        )
    for kind, cap in budget.kind_caps:
        over("budget-kind", f"{base}.kinds.{kind}", m["kinds"].get(kind, 0), cap, ERROR)
    over("budget-cost", f"{base}.cost", m["cost"], budget.max_cost, ERROR)
    over("budget-hops", f"{base}.hops", m["max_hops"], budget.max_hops, WARNING)
    over(
        "budget-locks",
        f"{base}.locks",
        m["locked_permille"],
        budget.max_locked_permille,
        WARNING,
    )
    over(
        "budget-rest-gap",
        f"{base}.rest",
        m["max_rest_gap"],
        budget.max_rest_gap,
        WARNING,
    )
    for rid in m["stranded"]:
        out.append(Finding("budget-no-rest-path", f"{base}.rest.{rid}", rid, WARNING))
    over(
        "budget-depth-step",
        f"{base}.depth_step",
        m["max_depth_step"],
        budget.max_depth_step,
        WARNING,
    )
    for boss, cost in m["boss_path_cost"].items():
        over(
            "budget-path-cost",
            f"{base}.path.{boss}",
            cost,
            budget.max_path_cost,
            WARNING,
        )
    return tuple(sorted(out, key=lambda f: (f.path, f.code)))


@dataclass(frozen=True)
class BudgetReport:
    era: str
    order: int
    digest: str
    metrics: dict[str, Any] = field(compare=True)
    findings: tuple[Finding, ...] = ()

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == WARNING)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "era": self.era,
            "order": self.order,
            "digest": self.digest,
            "ok": self.ok,
            "metrics": json.loads(json.dumps(self.metrics, sort_keys=True)),
            "findings": [f.as_dict() for f in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def evaluate(era: EraSpec, budget: EraBudget = DEFAULT_BUDGET) -> BudgetReport:
    """Measure ``era`` and check it against ``budget``."""
    era = _require_era(era)
    metrics = measure(era, budget)
    return BudgetReport(
        era=era.id,
        order=era.order,
        digest=digest(era),
        metrics=metrics,
        findings=check_budget(era, budget, metrics=metrics),
    )


@dataclass(frozen=True)
class CampaignReport:
    eras: tuple[BudgetReport, ...]
    totals: dict[str, Any]
    findings: tuple[Finding, ...] = ()

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.eras) and not any(
            f.severity == ERROR for f in self.findings
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "totals": json.loads(json.dumps(self.totals, sort_keys=True)),
            "findings": [f.as_dict() for f in self.findings],
            "eras": [r.as_dict() for r in self.eras],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def evaluate_campaign(
    eras: Iterable[EraSpec], budget: CampaignBudget = DEFAULT_CAMPAIGN_BUDGET
) -> CampaignReport:
    """Per-era reports in ``(order, id)`` order plus a campaign rollup."""
    if not isinstance(budget, CampaignBudget):
        raise SchemaError("bad-type", "budget", "expected CampaignBudget")
    items: list[EraSpec] = []
    seen: set[str] = set()
    for i, era in enumerate(eras):
        if not isinstance(era, EraSpec):
            raise SchemaError("bad-type", f"eras[{i}]", "expected EraSpec")
        if era.id in seen:
            raise SchemaError("duplicate-era", f"eras[{i}].id", era.id)
        seen.add(era.id)
        items.append(era)
    items.sort(key=lambda e: (e.order, e.id))
    reports = tuple(evaluate(e, budget.era) for e in items)
    out: list[Finding] = []
    total_rooms = sum(r.metrics["rooms"] for r in reports)
    total_cost = sum(r.metrics["cost"] for r in reports)
    if total_rooms > budget.max_total_rooms:
        out.append(
            Finding(
                "budget-total-rooms",
                "campaign.rooms",
                f"{total_rooms} > {budget.max_total_rooms}",
            )
        )
    if total_cost > budget.max_total_cost:
        out.append(
            Finding(
                "budget-total-cost",
                "campaign.cost",
                f"{total_cost} > {budget.max_total_cost}",
            )
        )
    if budget.rising_cost:
        for prev, cur in zip(reports, reports[1:]):
            if cur.metrics["cost"] < prev.metrics["cost"]:
                out.append(
                    Finding(
                        "difficulty-regression",
                        f"campaign.eras.{cur.era}",
                        f"cost {cur.metrics['cost']} < {prev.era} {prev.metrics['cost']}",
                        WARNING,
                    )
                )
    totals = {
        "eras": len(reports),
        "rooms": total_rooms,
        "cost": total_cost,
        "bosses": sum(r.metrics["bosses"] for r in reports),
        "cost_curve": [[r.era, r.metrics["cost"]] for r in reports],
        "errors": sum(len(r.errors) for r in reports)
        + sum(1 for f in out if f.severity == ERROR),
        "warnings": sum(len(r.warnings) for r in reports)
        + sum(1 for f in out if f.severity == WARNING),
    }
    return CampaignReport(eras=reports, totals=totals, findings=tuple(out))


def _read_budget(path: Path) -> CampaignBudget:
    if not path.is_file():
        raise SchemaError("missing-file", str(path), "not a file")
    if path.stat().st_size > MAX_BYTES:
        raise SchemaError("too-large", str(path), f"max {MAX_BYTES} bytes")
    try:
        data = json.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        raise SchemaError("bad-json", str(path), str(exc)) from None
    return CampaignBudget.from_dict(data)


def main(argv: Sequence[str] | None = None) -> int:
    """``era-budget FILE [FILE ...] [--budget FILE] [--campaign]``.

    Prints one JSON line per FILE (report or error); with ``--campaign`` adds
    a final rollup line. Exit 0 when nothing has ``error`` findings, 1 when
    something does or a FILE fails to load, 2 for a bad budget file. Local
    files only; never writes.
    """
    parser = argparse.ArgumentParser(
        prog="era-budget", description="Era pacing budget check"
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--campaign", action="store_true")
    args = parser.parse_args(argv)
    try:
        budget = _read_budget(args.budget) if args.budget else DEFAULT_CAMPAIGN_BUDGET
    except SchemaError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, sort_keys=True))
        return 2
    ok = True
    eras: list[EraSpec] = []
    for path in args.files:
        try:
            era = load_era_json(path)
        except SchemaError as exc:
            ok = False
            print(
                json.dumps(
                    {"file": str(path), "ok": False, "error": exc.as_dict()},
                    sort_keys=True,
                )
            )
            continue
        eras.append(era)
        report = evaluate(era, budget.era)
        ok = ok and report.ok
        line = report.as_dict()
        line["file"] = str(path)
        print(json.dumps(line, sort_keys=True, separators=(",", ":")))
    if args.campaign:
        try:
            camp = evaluate_campaign(eras, budget)
        except SchemaError as exc:
            print(
                json.dumps(
                    {"campaign": True, "ok": False, "error": exc.as_dict()},
                    sort_keys=True,
                )
            )
            return 1
        ok = ok and camp.ok
        line = {
            "campaign": True,
            "ok": camp.ok,
            "totals": camp.as_dict()["totals"],
            "findings": camp.as_dict()["findings"],
        }
        print(json.dumps(line, sort_keys=True, separators=(",", ":")))
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
