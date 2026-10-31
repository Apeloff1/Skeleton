"""Crafting and industry over the gameplay economy.

:class:`IndustrySystem` runs blueprints, multi-step chains, research and
extraction on top of a :class:`~skeleton.economy.gameplay.core.GameplayEconomy`
and, optionally, a :class:`~skeleton.economy.gameplay.market.exchange.PlayerMarket`.
It never creates or destroys money or items on its own; every flow goes
through a declared economy path so the existing ledgers stay authoritative:

* **Item faucets.** Extraction mints through ``grant_items`` under
  ``extract:<node>``; finished builds mint their output under ``craft``.
* **Item sinks.** Inputs are burned under ``craft_input`` when a build
  starts; crafting waste is burned under ``craft_loss`` at the same time.
* **Money sinks.** An install fee (``install_sink``, flat + bps of the
  output's market value) is burned when a job is queued; research cost
  (``research_sink``) is burned when research is queued. Neither is
  refunded on cancel — both are sinks by design.
* **Time.** Only ticks passed in by the caller move jobs; completions are
  processed in ``(end, job_id)`` order and a freed line restarts work at the
  completion tick, so outcomes do not depend on how often ``advance`` runs.

The command log replays to the same :meth:`digest` (see :mod:`.replay`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.economy.gameplay.core import GameplayEconomy
from skeleton.economy.gameplay.industry.blueprints import Blueprint, BlueprintBook
from skeleton.economy.gameplay.industry.errors import (
    IndustryConservationError,
    IndustryError,
    JobRejected,
)
from skeleton.economy.gameplay.industry.extraction import ExtractionNode, NodeSpec
from skeleton.economy.gameplay.industry.jobs import (
    BUILD,
    CANCELLED,
    DELIVERED,
    DONE,
    QUEUED,
    RESEARCH,
    RUNNING,
    BuildQueue,
    Job,
)
from skeleton.economy.gameplay.industry.research import (
    TRACKS,
    ResearchCurve,
    ResearchLevels,
)
from skeleton.economy.gameplay.industry.telemetry import IndustryTelemetry
from skeleton.simulation.economy.sim import _req_id, _req_int

CRAFT_SOURCE = "craft"
CRAFT_INPUT_SINK = "craft_input"
CRAFT_LOSS_SINK = "craft_loss"


@dataclass(frozen=True)
class IndustryConfig:
    currency: str
    install_sink: str
    research_sink: str
    period_ticks: int = 100
    default_lines: int = 2
    max_runs: int = 1_000
    research_curve: ResearchCurve = field(default_factory=ResearchCurve)

    def __post_init__(self) -> None:
        _req_id(self.currency, "currency")
        _req_id(self.install_sink, "install_sink")
        _req_id(self.research_sink, "research_sink")
        _req_int(self.period_ticks, "period_ticks", minimum=1)
        _req_int(self.default_lines, "default_lines", minimum=1)
        _req_int(self.max_runs, "max_runs", minimum=1)
        if self.install_sink == self.research_sink:
            raise IndustryError("install and research sinks must differ")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["research_curve"] = self.research_curve.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IndustryConfig":
        kw = dict(data)
        kw["research_curve"] = ResearchCurve(**kw["research_curve"])
        return cls(**kw)


class IndustrySystem:
    def __init__(
        self,
        econ: GameplayEconomy,
        config: IndustryConfig,
        blueprints: Iterable[Blueprint] = (),
        nodes: Iterable[NodeSpec] = (),
        *,
        market: Any = None,
    ) -> None:
        self.econ = econ
        self.config = config
        self.market = market
        self._validate()
        self.book = BlueprintBook(blueprints, items=econ.items)
        self.nodes: dict[str, ExtractionNode] = {}
        for spec in nodes:
            self.add_node(spec)
        self.queue = BuildQueue(config.default_lines)
        self.research = ResearchLevels()
        self.telemetry = IndustryTelemetry(config.period_ticks)
        self.log: list[dict[str, Any]] = []
        self._tick = 0
        self._next_chain = 1

    # -- validation ---------------------------------------------------------
    def _validate(self) -> None:
        cfg, econ = self.config, self.econ
        if cfg.currency not in econ.currencies:
            raise IndustryError("industry currency is not an economy currency")
        for sink_id in (cfg.install_sink, cfg.research_sink):
            spec = econ.sinks.get(sink_id)
            if spec is None or spec.currency != cfg.currency:
                raise IndustryError(
                    f"{sink_id!r} must be a declared sink of {cfg.currency!r}"
                )
        if self.market is not None:
            mcfg = self.market.config
            if self.market.econ is not econ:
                raise IndustryError("market runs on a different economy")
            if mcfg.currency != cfg.currency:
                raise IndustryError("market and industry currencies differ")
            if {cfg.install_sink, cfg.research_sink} & {
                mcfg.listing_sink,
                mcfg.sales_tax_sink,
            }:
                raise IndustryError("industry sinks must not be market sinks")

    def add_node(self, spec: NodeSpec) -> None:
        if spec.node_id in self.nodes:
            raise IndustryError(f"duplicate node {spec.node_id!r}")
        if spec.item not in self.econ.items:
            raise IndustryError(f"node mines unknown item {spec.item!r}")
        self.nodes[spec.node_id] = ExtractionNode(spec)

    def _owner(self, owner: str) -> None:
        _req_id(owner, "owner")
        if owner not in self.econ.owners():
            raise JobRejected("no such owner")
        if self.market is not None and owner == _escrow_owner():
            raise JobRejected("reserved owner")

    # -- prices --------------------------------------------------------------
    def value_of(self, item_id: str) -> int:
        """Unit value: market last print, else market reference, else vendor mid, else 0."""
        if self.market is not None:
            last = self.market.history.last_price(item_id)
            if last is not None:
                return int(last)
            ref = self.market.monitor.reference(item_id)
            if ref is not None:
                return int(ref)
        spec = self.econ.items[item_id]
        if spec.vendor_buy_price is not None and spec.vendor_sell_price is not None:
            return (spec.vendor_buy_price + spec.vendor_sell_price) // 2
        return 0

    def install_fee(self, blueprint_id: str, runs: int) -> int:
        bp = self.book.get(blueprint_id)
        base = self.value_of(bp.output) * bp.output_qty * runs
        return self.econ.sinks[self.config.install_sink].amount_for(base)

    def research_cost(self, owner: str, blueprint_id: str, track: str) -> int:
        target = self.research.level(owner, blueprint_id, track) + 1
        target += self.queue.pending_research(owner, blueprint_id, track)
        return self.config.research_curve.cost(target)

    # -- clock -----------------------------------------------------------------
    def _clock(self, tick: int) -> None:
        _req_int(tick, "tick")
        if tick < self._tick:
            raise IndustryError("tick went backwards")
        self._tick = tick
        pending = self.telemetry.pending_period()
        if pending is not None and self.telemetry.period_of(tick) > pending:
            self._close(pending)

    def _close(self, period: int) -> dict[str, int]:
        supply = self.econ.flow_report(self.config.currency)["circulating"]
        index = None
        if self.market is not None:
            index = self.market.telemetry.price_index()
        return self.telemetry.close(period, supply, index)

    def advance(self, tick: int) -> list[dict[str, Any]]:
        """Run every completion due by ``tick``; returns finished jobs."""
        with self.econ._lock:
            finished = self._run_until(tick)
            self.log.append({"op": "advance", "tick": tick})
            return finished

    def _run_until(self, tick: int) -> list[dict[str, Any]]:
        _req_int(tick, "tick")
        if tick < self._tick:
            raise IndustryError("tick went backwards")
        finished: list[dict[str, Any]] = []
        while True:
            job = self.queue.next_completion(tick)
            if job is None:
                break
            self._clock(job.end)
            self._complete(job)
            finished.append(job.to_dict())
            self._start_ready(job.end)
        self._clock(tick)
        self._start_ready(tick)
        return finished

    # -- queueing ----------------------------------------------------------------
    def set_lines(self, owner: str, lines: int) -> None:
        with self.econ._lock:
            self._owner(owner)
            _req_int(lines, "lines", minimum=1)
            self.queue.lines[owner] = lines
            self.log.append({"op": "set_lines", "owner": owner, "lines": lines})

    def queue_build(
        self, owner: str, blueprint_id: str, runs: int, tick: int
    ) -> dict[str, Any]:
        with self.econ._lock:
            self._owner(owner)
            bp = self.book.get(blueprint_id)
            _req_int(runs, "runs", minimum=1)
            if runs > self.config.max_runs:
                raise JobRejected("too many runs")
            self._run_until(tick)
            fee = self.install_fee(bp.blueprint_id, runs)
            if self.econ.balance(owner, self.config.currency) < fee:
                raise JobRejected("insufficient funds for install fee")
            job = self._new_build(owner, bp, runs, tick, (), None, fee)
            self._start_ready(tick)
            self.log.append(
                {
                    "op": "build",
                    "owner": owner,
                    "bp": blueprint_id,
                    "runs": runs,
                    "tick": tick,
                }
            )
            return job.to_dict()

    def _new_build(
        self,
        owner: str,
        bp: Blueprint,
        runs: int,
        tick: int,
        deps: tuple[int, ...],
        chain: int | None,
        fee: int,
    ) -> Job:
        if fee:
            self.econ.charge(
                self.config.install_sink,
                owner,
                self.value_of(bp.output) * bp.output_qty * runs,
            )
            self.telemetry.bump(tick, install_fees=fee)
        return self.queue.add(
            Job(
                job_id=self.queue.new_id(),
                owner=owner,
                kind=BUILD,
                blueprint_id=bp.blueprint_id,
                runs=runs,
                deps=deps,
                chain_id=chain,
                created=tick,
                output=bp.output,
                output_qty=bp.output_qty * runs,
                fee=fee,
            )
        )

    def plan(self, owner: str, target: str, qty: int) -> dict[str, Any]:
        return self.book.plan(target, qty, self.research.for_owner(owner)).to_dict()

    def queue_chain(
        self, owner: str, target: str, qty: int, tick: int
    ) -> dict[str, Any]:
        """Queue every step needed for ``qty`` of ``target``; returns the chain."""
        with self.econ._lock:
            self._owner(owner)
            self._run_until(tick)
            plan = self.book.plan(target, qty, self.research.for_owner(owner))
            fees = [self.install_fee(s.blueprint_id, s.runs) for s in plan.steps]
            if any(s.runs > self.config.max_runs for s in plan.steps):
                raise JobRejected("too many runs")
            if self.econ.balance(owner, self.config.currency) < sum(fees):
                raise JobRejected("insufficient funds for install fees")
            chain = self._next_chain
            self._next_chain += 1
            job_for: dict[str, int] = {}
            jobs = []
            for step, fee in zip(plan.steps, fees):
                bp = self.book.get(step.blueprint_id)
                deps = tuple(sorted(job_for[i] for i, _ in bp.inputs if i in job_for))
                job = self._new_build(owner, bp, step.runs, tick, deps, chain, fee)
                job_for[bp.output] = job.job_id
                jobs.append(job.job_id)
            self._start_ready(tick)
            self.log.append(
                {
                    "op": "chain",
                    "owner": owner,
                    "target": target,
                    "qty": qty,
                    "tick": tick,
                }
            )
            return {
                "chain_id": chain,
                "jobs": jobs,
                "plan": plan.to_dict(),
                "fees": sum(fees),
            }

    def queue_research(
        self, owner: str, blueprint_id: str, track: str, tick: int
    ) -> dict[str, Any]:
        with self.econ._lock:
            self._owner(owner)
            bp = self.book.get(blueprint_id)
            if track not in TRACKS:
                raise JobRejected("track must be 'me' or 'te'")
            self._run_until(tick)
            current = self.research.level(owner, blueprint_id, track)
            pending = self.queue.pending_research(owner, blueprint_id, track)
            if current + pending >= bp.max_research:
                raise JobRejected("research level at cap")
            cost = self.research_cost(owner, blueprint_id, track)
            if self.econ.balance(owner, self.config.currency) < cost:
                raise JobRejected("insufficient funds for research")
            self.econ.charge_amount(self.config.research_sink, owner, cost)
            self.telemetry.bump(tick, research_spend=cost)
            job = self.queue.add(
                Job(
                    job_id=self.queue.new_id(),
                    owner=owner,
                    kind=RESEARCH,
                    blueprint_id=blueprint_id,
                    track=track,
                    created=tick,
                    fee=cost,
                )
            )
            self._start_ready(tick)
            self.log.append(
                {
                    "op": "research",
                    "owner": owner,
                    "bp": blueprint_id,
                    "track": track,
                    "tick": tick,
                }
            )
            return job.to_dict()

    def cancel(self, owner: str, job_id: int, tick: int) -> dict[str, Any]:
        """Cancel a queued job (fees are sinks and stay burned). Dependents cancel too."""
        with self.econ._lock:
            self._run_until(tick)
            job = self.queue.jobs.get(job_id)
            if job is None or job.owner != owner:
                raise JobRejected("no such job")
            if job.status != QUEUED:
                raise JobRejected("only queued jobs can be cancelled")
            job.status = CANCELLED
            cancelled = [job_id] + self._cascade_cancel()
            self._start_ready(tick)
            self.log.append(
                {"op": "cancel", "owner": owner, "job_id": job_id, "tick": tick}
            )
            return {"cancelled": cancelled}

    def _cascade_cancel(self) -> list[int]:
        out = []
        changed = True
        while changed:
            changed = False
            for job in self.queue.queued():
                if self.queue.deps_failed(job):
                    job.status = CANCELLED
                    out.append(job.job_id)
                    changed = True
        return out

    # -- running -----------------------------------------------------------------------
    def _start_ready(self, now: int) -> None:
        for job in self.queue.queued():
            if not self.queue.free_line(job.owner) or not self.queue.deps_ready(job):
                continue
            if job.kind == BUILD:
                self._try_start_build(job, now)
            else:
                self._start(
                    job,
                    now,
                    self.config.research_curve.ticks(
                        self.research.level(job.owner, job.blueprint_id, job.track) + 1
                    ),
                )

    def _start(self, job: Job, now: int, ticks: int) -> None:
        job.status = RUNNING
        job.start = now
        job.end = now + ticks
        self.telemetry.bump(now, jobs_started=1)

    def _try_start_build(self, job: Job, now: int) -> None:
        bp = self.book.get(job.blueprint_id)
        me, te = self.research.levels(job.owner, bp.blueprint_id)
        mats = bp.materials(job.runs, me)
        inv = self.econ.inventory(job.owner)
        if any(inv.count(i) < r["used"] + r["lost"] for i, r in mats.items()):
            return  # blocked on materials; stays queued
        consumed = lost = lost_value = 0
        for item_id, row in sorted(mats.items()):
            self.econ.consume_items(CRAFT_INPUT_SINK, job.owner, item_id, row["used"])
            consumed += row["used"]
            if row["lost"]:
                self.econ.consume_items(
                    CRAFT_LOSS_SINK, job.owner, item_id, row["lost"]
                )
                lost += row["lost"]
                lost_value += row["lost"] * self.value_of(item_id)
        job.me, job.te = me, te
        job.used = {i: r["used"] for i, r in mats.items()}
        job.lost = {i: r["lost"] for i, r in mats.items() if r["lost"]}
        self._start(job, now, bp.ticks_at(te, job.runs))
        self.telemetry.bump(now, consumed=consumed, lost=lost, lost_value=lost_value)

    def _complete(self, job: Job) -> None:
        self.telemetry.bump(job.end, jobs_done=1)
        if job.kind == RESEARCH:
            bp = self.book.get(job.blueprint_id)
            self.research.raise_level(
                job.owner, job.blueprint_id, job.track, bp.max_research
            )
            job.status = DELIVERED
            return
        job.status = DONE
        self._deliver(job, job.end)

    def _deliver(self, job: Job, tick: int) -> bool:
        if not self.econ.fits_many(job.owner, {job.output: job.output_qty}):
            return False
        self.econ.grant_items(CRAFT_SOURCE, job.owner, job.output, job.output_qty)
        job.status = DELIVERED
        self.telemetry.bump(
            tick,
            crafted=job.output_qty,
            crafted_value=job.output_qty * self.value_of(job.output),
        )
        return True

    def collect(self, owner: str, job_id: int, tick: int) -> int:
        """Deliver a finished build whose output did not fit at completion."""
        with self.econ._lock:
            self._run_until(tick)
            job = self.queue.jobs.get(job_id)
            if job is None or job.owner != owner or job.status != DONE:
                raise JobRejected("nothing to collect")
            if not self._deliver(job, tick):
                raise JobRejected("inventory full")
            self._start_ready(tick)
            self.log.append(
                {"op": "collect", "owner": owner, "job_id": job_id, "tick": tick}
            )
            return job.output_qty

    # -- extraction ---------------------------------------------------------------------
    def extract(self, owner: str, node_id: str, tick: int) -> int:
        with self.econ._lock:
            self._owner(owner)
            node = self.nodes.get(node_id)
            if node is None:
                raise IndustryError("no such node")
            self._run_until(tick)
            qty = node.extract(self.econ, owner, tick)
            self.telemetry.bump(tick, extracted=qty)
            self._start_ready(tick)
            self.log.append(
                {"op": "extract", "owner": owner, "node": node_id, "tick": tick}
            )
            return qty

    # -- market ----------------------------------------------------------------------------
    def list_output(
        self, owner: str, item_id: str, qty: int, unit_price: int, tick: int
    ) -> dict[str, Any]:
        """Sell crafted goods on the attached player market (fees/tax are market sinks)."""
        if self.market is None:
            raise IndustryError("no market attached")
        with self.econ._lock:
            self._run_until(tick)
            result = self.market.place(owner, "sell", item_id, qty, unit_price, tick)
            self.log.append(
                {
                    "op": "list",
                    "owner": owner,
                    "item": item_id,
                    "qty": qty,
                    "price": unit_price,
                    "tick": tick,
                }
            )
            return result

    def buy_inputs(
        self, owner: str, item_id: str, qty: int, unit_price: int, tick: int
    ) -> dict[str, Any]:
        """Place an IOC buy on the attached market to source inputs for a build."""
        if self.market is None:
            raise IndustryError("no market attached")
        with self.econ._lock:
            self._run_until(tick)
            result = self.market.place(
                owner, "buy", item_id, qty, unit_price, tick, tif="ioc"
            )
            self._start_ready(tick)
            self.log.append(
                {
                    "op": "buy",
                    "owner": owner,
                    "item": item_id,
                    "qty": qty,
                    "price": unit_price,
                    "tick": tick,
                }
            )
            return result

    # -- inspection ---------------------------------------------------------------------
    def jobs(self, owner: str | None = None) -> list[dict[str, Any]]:
        rows = self.queue.ordered() if owner is None else self.queue.of(owner)
        return [j.to_dict() for j in rows]

    def sink_report(self) -> dict[str, int]:
        cur = self.econ.flow_report(self.config.currency)["by_sink"]
        return {
            "install_fees": cur.get(self.config.install_sink, 0),
            "research_spend": cur.get(self.config.research_sink, 0),
            "craft_input_units": sum(
                self.econ.item_report(i)["by_sink"].get(CRAFT_INPUT_SINK, 0)
                for i in sorted(self.econ.items)
            ),
            "craft_loss_units": sum(
                self.econ.item_report(i)["by_sink"].get(CRAFT_LOSS_SINK, 0)
                for i in sorted(self.econ.items)
            ),
        }

    def audit(self) -> dict[str, Any]:
        """Industry books against the economy's ledgers. ``ok`` = all checks."""
        with self.econ._lock:
            used: dict[str, int] = {}
            lost: dict[str, int] = {}
            crafted: dict[str, int] = {}
            fees = research = 0
            for job in self.queue.ordered():
                if job.kind == BUILD:
                    fees += job.fee
                    for i, q in job.used.items():
                        used[i] = used.get(i, 0) + q
                    for i, q in job.lost.items():
                        lost[i] = lost.get(i, 0) + q
                    if job.status == DELIVERED:
                        crafted[job.output] = (
                            crafted.get(job.output, 0) + job.output_qty
                        )
                else:
                    research += job.fee
            mismatched: list[str] = []
            for item_id in sorted(self.econ.items):
                rep = self.econ.item_report(item_id)
                if rep["by_sink"].get(CRAFT_INPUT_SINK, 0) != used.get(item_id, 0):
                    mismatched.append(f"{item_id}:input")
                if rep["by_sink"].get(CRAFT_LOSS_SINK, 0) != lost.get(item_id, 0):
                    mismatched.append(f"{item_id}:loss")
                if rep["by_source"].get(CRAFT_SOURCE, 0) != crafted.get(item_id, 0):
                    mismatched.append(f"{item_id}:craft")
            nodes_ok = True
            for node in self.nodes.values():
                rep = self.econ.item_report(node.spec.item)
                if rep["by_source"].get(node.spec.source, 0) != node.extracted:
                    nodes_ok = False
                if (
                    node.remaining + node.extracted != node.spec.reserve
                    or node.remaining < 0
                ):
                    nodes_ok = False
            sinks = self.sink_report()
            checks = {
                "economy": self.econ.audit()["ok"],
                "items": self.econ.item_audit()["ok"],
                "materials": not mismatched,
                "nodes": nodes_ok,
                "install_fees": sinks["install_fees"]
                == fees
                == self.telemetry.totals["install_fees"],
                "research_spend": sinks["research_spend"]
                == research
                == self.telemetry.totals["research_spend"],
            }
            if self.market is not None:
                checks["market"] = self.market.audit()["ok"]
            return {
                "ok": all(checks.values()),
                "checks": checks,
                "mismatched": mismatched,
            }

    def require_conserved(self) -> None:
        report = self.audit()
        if not report["ok"]:
            raise IndustryConservationError(
                f"industry books do not balance: {report['checks']}"
            )

    # -- state ----------------------------------------------------------------------------
    def to_state(self) -> dict[str, Any]:
        with self.econ._lock:
            return {
                "config": self.config.to_dict(),
                "blueprints": self.book.to_state(),
                "nodes": [self.nodes[n].to_state() for n in sorted(self.nodes)],
                "queue": self.queue.to_state(),
                "research": self.research.to_state(),
                "telemetry": self.telemetry.to_state(),
                "tick": self._tick,
                "next_chain": self._next_chain,
            }

    @classmethod
    def from_state(
        cls, econ: GameplayEconomy, state: Mapping[str, Any], *, market: Any = None
    ) -> "IndustrySystem":
        config = IndustryConfig.from_dict(state["config"])
        system = cls(econ, config, market=market)
        system.book = BlueprintBook.from_state(state["blueprints"], items=econ.items)
        for row in state["nodes"]:
            node = ExtractionNode.from_state(row)
            system.nodes[node.spec.node_id] = node
        system.queue = BuildQueue.from_state(state["queue"])
        system.research = ResearchLevels.from_state(state["research"])
        system.telemetry = IndustryTelemetry.from_state(state["telemetry"])
        system._tick = int(state["tick"])
        system._next_chain = int(state["next_chain"])
        return system

    def digest(self) -> str:
        """sha256 over economy snapshot plus industry state (replay contract)."""
        payload = json.dumps(
            {"econ": self.econ.snapshot(), "industry": self.to_state()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _escrow_owner() -> str:
    from skeleton.economy.gameplay.market.exchange import ESCROW_OWNER

    return ESCROW_OWNER


__all__ = [
    "CRAFT_INPUT_SINK",
    "CRAFT_LOSS_SINK",
    "CRAFT_SOURCE",
    "IndustryConfig",
    "IndustrySystem",
]
