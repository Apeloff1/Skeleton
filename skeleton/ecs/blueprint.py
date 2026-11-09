"""Blueprint → ECS adapter.

Turns a Forge blueprint (the ``POST /api/skeleton/compose`` result, its
``topology`` dict, or a :class:`skeleton.forge.universal.Blueprint`) into a
runnable :class:`~skeleton.simulation.ecs.live.LiveWorld` plus
:class:`~skeleton.simulation.ecs.ticker.TickScheduler`:

* every blueprint component becomes one entity carrying the component set of
  its ``kind`` (see :data:`KIND_CATALOG`) plus a ``node`` record
  (instance id, kind, feature, config);
* every wire ``(src, port) → (dst, port)`` becomes an event channel named
  ``"<src>.<port>"``; the destination's system reads it;
* every kind contributes a deterministic built-in system, ordered after the
  systems that feed it so a signal crosses the whole graph in one tick;
* optional sandboxed scripts (keyed by instance id or kind) are attached as
  extra systems with declared access.

The adapter is pure and deterministic: identical blueprints and seeds give
identical worlds, schedules and state digests.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from skeleton.simulation.ecs.errors import ValidationError
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.ticker import SystemContext, SystemDef, TickScheduler

from .script import CompiledScript, compile_script
from .script_system import script_system

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
MAX_COMPONENTS = 256
MAX_WIRES = 1024


class BlueprintAdapterError(ValidationError):
    code = "SIM.ECS.BLUEPRINT_ADAPTER"


@dataclass(frozen=True)
class KindSpec:
    """ECS shape of one blueprint component kind."""

    components: Mapping[str, Any]
    outputs: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    description: str = ""


KIND_CATALOG: dict[str, KindSpec] = {
    "player": KindSpec({"intent": {"rate": 1, "emitted": 0}, "stats": {"hp": 100, "haul": 0, "actions": 0}}, outputs=("intent", "state"), description="player avatar emitting intent and state"),
    "enemy_spawner": KindSpec({"spawner": {"pressure": 0.0, "spawned": 0, "every": 3}}, outputs=("spawn",), inputs=("tick",), description="hostile pressure scaling with player intent"),
    "weapon_forge": KindSpec({"forge": {"parts": 0, "weapons": 0, "cost": 3}}, outputs=("weapon",), inputs=("parts",), description="turns parts into weapons"),
    "heat": KindSpec({"heat": {"level": 0.0, "decay": 0.05, "gain": 1.0, "alarm": 10.0, "alarmed": False}}, outputs=("alarm",), inputs=("in",), description="escalation meter"),
    "collapse": KindSpec({"clock": {"remaining": 600, "per_tick": 1, "failed": False}}, outputs=("failed",), inputs=("tick",), description="run-ending fail clock"),
    "extract": KindSpec({"extract": {"goal": 5, "done": False}}, outputs=("won",), description="win condition"),
    "jeeves": KindSpec({"advisor": {"advice": "", "seen": 0}}, inputs=("telemetry",), description="tactical companion"),
    "state_store": KindSpec({"vault": {"writes": 0, "last": None}}, inputs=("write",), description="persistent state"),
    "sink": KindSpec({"readout": {"count": 0, "last": None}}, inputs=("in",), description="player-facing readout"),
}
GENERIC_KIND = KindSpec({"generic": {"received": 0}}, description="unknown kind: counts inbound signals")


@dataclass(frozen=True)
class NodeSpec:
    instance_id: str
    kind: str
    config: Mapping[str, Any]


@dataclass(frozen=True)
class WireSpec:
    src: tuple[str, str]
    dst: tuple[str, str]

    @property
    def channel(self) -> str:
        return f"{self.src[0]}.{self.src[1]}"


@dataclass(frozen=True)
class NormalBlueprint:
    blueprint_id: str
    nodes: tuple[NodeSpec, ...]
    wires: tuple[WireSpec, ...]

    def node(self, instance_id: str) -> NodeSpec:
        for n in self.nodes:
            if n.instance_id == instance_id:
                return n
        raise BlueprintAdapterError("unknown node", context={"instance_id": instance_id})

    def inbound(self, instance_id: str) -> tuple[WireSpec, ...]:
        return tuple(w for w in self.wires if w.dst[0] == instance_id)

    def fingerprint(self) -> str:
        record = {
            "id": self.blueprint_id,
            "nodes": [[n.instance_id, n.kind, _canon(n.config)] for n in self.nodes],
            "wires": [[list(w.src), list(w.dst)] for w in self.wires],
        }
        return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _canon(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _ident(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise BlueprintAdapterError(f"invalid {label}", context={label: repr(value)[:80]})
    return value


def _pair(value: Any, label: str) -> tuple[str, str]:
    if isinstance(value, Mapping):
        value = (value.get("component") or value.get("instance_id"), value.get("port"))
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise BlueprintAdapterError(f"{label} must be [component, port]")
    return _ident(value[0], "component id"), _ident(value[1], "port name")


def normalize_blueprint(source: Any) -> NormalBlueprint:
    """Accept a compose result, a topology dict or a universal ``Blueprint``."""
    if hasattr(source, "components") and hasattr(source, "wires") and not isinstance(source, Mapping):
        comps = [
            {"instance_id": c.instance_id, "kind": c.kind, "config": dict(getattr(c, "config", {}) or {})}
            for c in source.components.values()
        ]
        wires = [{"from": list(w.src), "to": list(w.dst)} for w in source.wires]
        source = {"blueprint_id": getattr(source, "blueprint_id", ""), "components": comps, "wires": wires}
    if not isinstance(source, Mapping):
        raise BlueprintAdapterError("blueprint must be a mapping or Blueprint")
    topology = source.get("topology")
    raw_components = source.get("components")
    if isinstance(topology, Mapping) and isinstance(topology.get("components"), Mapping):
        raw_components = topology["components"]
    nodes: list[NodeSpec] = []
    if isinstance(raw_components, Mapping):
        items = [{"instance_id": k, **(dict(v) if isinstance(v, Mapping) else {})} for k, v in raw_components.items()]
    elif isinstance(raw_components, list):
        items = raw_components
    else:
        raise BlueprintAdapterError("blueprint has no components")
    if len(items) > MAX_COMPONENTS:
        raise BlueprintAdapterError("too many components", context={"maximum": MAX_COMPONENTS})
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise BlueprintAdapterError("component entries must be mappings")
        iid = _ident(item.get("instance_id"), "component id")
        if iid in seen:
            raise BlueprintAdapterError("duplicate component id", context={"instance_id": iid})
        seen.add(iid)
        kind = _ident(item.get("kind"), "component kind")
        config = dict(item.get("config") or {})
        if "feature" in item and "feature" not in config:
            config["feature"] = item["feature"]
        nodes.append(NodeSpec(iid, kind, _canon(config)))
    raw_wires = source.get("wires") or (topology.get("wires") if isinstance(topology, Mapping) else None) or []
    if not isinstance(raw_wires, list) or len(raw_wires) > MAX_WIRES:
        raise BlueprintAdapterError("wires must be a bounded list", context={"maximum": MAX_WIRES})
    wires: list[WireSpec] = []
    for w in raw_wires:
        if not isinstance(w, Mapping):
            raise BlueprintAdapterError("wire entries must be mappings")
        src = _pair(w.get("from", w.get("src")), "wire source")
        dst = _pair(w.get("to", w.get("dst")), "wire destination")
        for end in (src, dst):
            if end[0] not in seen:
                raise BlueprintAdapterError("wire references unknown component", context={"component": end[0]})
        wires.append(WireSpec(src, dst))
    bp_id = source.get("blueprint_id") or (topology.get("blueprint_id") if isinstance(topology, Mapping) else "") or ""
    return NormalBlueprint(str(bp_id)[:128], tuple(nodes), tuple(wires))


# ---------------------------------------------------------------------------
# built-in kind systems
# ---------------------------------------------------------------------------
KindSystem = Callable[[SystemContext, int, "NodeIO"], None]


@dataclass(frozen=True)
class NodeIO:
    """Channels a node reads (inbound wires) and writes (its output ports)."""

    instance_id: str
    inputs: Mapping[str, tuple[str, ...]]  # port -> channels
    outputs: Mapping[str, str]  # port -> channel

    def read(self, ctx: SystemContext, port: str) -> list[Any]:
        out: list[Any] = []
        for channel in self.inputs.get(port, ()):
            out.extend(ctx.read(channel))
        return out

    def read_all(self, ctx: SystemContext) -> list[Any]:
        out: list[Any] = []
        for port in sorted(self.inputs):
            out.extend(self.read(ctx, port))
        return out

    def emit(self, ctx: SystemContext, port: str, payload: Any) -> None:
        channel = self.outputs.get(port)
        if channel is not None:
            ctx.send(channel, payload)


def _player(ctx: SystemContext, e: int, io: NodeIO) -> None:
    intent = dict(ctx.get(e, "intent"))
    stats = dict(ctx.get(e, "stats"))
    if ctx.tick % max(1, int(intent.get("rate", 1))) == 0:
        intent["emitted"] = int(intent.get("emitted", 0)) + 1
        stats["actions"] = int(stats.get("actions", 0)) + 1
        roll = ctx.rng.random()
        if roll < 0.35:
            stats["haul"] = int(stats.get("haul", 0)) + 1
        io.emit(ctx, "intent", {"tick": ctx.tick, "roll": round(roll, 6)})
    io.emit(ctx, "state", {"tick": ctx.tick, "hp": stats.get("hp"), "haul": stats.get("haul")})
    ctx.set(e, "intent", intent)
    ctx.set(e, "stats", stats)


def _spawner(ctx: SystemContext, e: int, io: NodeIO) -> None:
    sp = dict(ctx.get(e, "spawner"))
    signals = io.read_all(ctx)
    sp["pressure"] = round(float(sp.get("pressure", 0.0)) + 0.25 * len(signals), 6)
    every = max(1, int(sp.get("every", 3)))
    if signals and sp["pressure"] >= every:
        sp["pressure"] = round(sp["pressure"] - every, 6)
        sp["spawned"] = int(sp.get("spawned", 0)) + 1
        ctx.commands.spawn({"hostile": {"from": io.instance_id, "tick": ctx.tick}})
        io.emit(ctx, "spawn", {"tick": ctx.tick, "n": sp["spawned"]})
    ctx.set(e, "spawner", sp)


def _forge(ctx: SystemContext, e: int, io: NodeIO) -> None:
    fg = dict(ctx.get(e, "forge"))
    fg["parts"] = int(fg.get("parts", 0)) + len(io.read_all(ctx))
    cost = max(1, int(fg.get("cost", 3)))
    while fg["parts"] >= cost:
        fg["parts"] -= cost
        fg["weapons"] = int(fg.get("weapons", 0)) + 1
        io.emit(ctx, "weapon", {"tick": ctx.tick, "n": fg["weapons"]})
    ctx.set(e, "forge", fg)


def _heat(ctx: SystemContext, e: int, io: NodeIO) -> None:
    h = dict(ctx.get(e, "heat"))
    gain = float(h.get("gain", 1.0)) * len(io.read_all(ctx))
    level = max(0.0, float(h.get("level", 0.0)) + gain - float(h.get("decay", 0.05)))
    h["level"] = round(level, 6)
    alarmed = level >= float(h.get("alarm", 10.0))
    if alarmed and not h.get("alarmed"):
        io.emit(ctx, "alarm", {"tick": ctx.tick, "level": h["level"]})
    h["alarmed"] = alarmed
    ctx.set(e, "heat", h)


def _collapse(ctx: SystemContext, e: int, io: NodeIO) -> None:
    c = dict(ctx.get(e, "clock"))
    if c.get("failed"):
        return
    ticks = len(io.read_all(ctx)) if io.inputs else 1
    c["remaining"] = max(0, int(c.get("remaining", 0)) - ticks * int(c.get("per_tick", 1)))
    if c["remaining"] == 0:
        c["failed"] = True
        io.emit(ctx, "failed", {"tick": ctx.tick})
        ctx.set_resource("outcome", {"result": "collapsed", "tick": ctx.tick})
    ctx.set(e, "clock", c)


def _extract(ctx: SystemContext, e: int, io: NodeIO) -> None:
    x = dict(ctx.get(e, "extract"))
    if x.get("done"):
        return
    haul = 0
    for _, stats in ctx.query("stats"):
        haul = max(haul, int(stats.get("haul", 0)))
    if haul >= int(x.get("goal", 5)):
        x["done"] = True
        io.emit(ctx, "won", {"tick": ctx.tick, "haul": haul})
        if ctx.resource("outcome", None) is None:
            ctx.set_resource("outcome", {"result": "extracted", "tick": ctx.tick})
    ctx.set(e, "extract", x)


def _jeeves(ctx: SystemContext, e: int, io: NodeIO) -> None:
    a = dict(ctx.get(e, "advisor"))
    seen = io.read_all(ctx)
    if seen:
        last = seen[-1] if isinstance(seen[-1], Mapping) else {}
        haul = int(last.get("haul") or 0)
        a["advice"] = "extract now" if haul >= 4 else "keep scavenging" if haul else "find parts"
        a["seen"] = int(a.get("seen", 0)) + len(seen)
    ctx.set(e, "advisor", a)


def _vault(ctx: SystemContext, e: int, io: NodeIO) -> None:
    v = dict(ctx.get(e, "vault"))
    writes = io.read_all(ctx)
    if writes:
        v["writes"] = int(v.get("writes", 0)) + len(writes)
        v["last"] = writes[-1]
    ctx.set(e, "vault", v)


def _sink(ctx: SystemContext, e: int, io: NodeIO) -> None:
    r = dict(ctx.get(e, "readout"))
    got = io.read_all(ctx)
    if got:
        r["count"] = int(r.get("count", 0)) + len(got)
        r["last"] = got[-1]
    ctx.set(e, "readout", r)


def _generic(ctx: SystemContext, e: int, io: NodeIO) -> None:
    g = dict(ctx.get(e, "generic"))
    g["received"] = int(g.get("received", 0)) + len(io.read_all(ctx))
    ctx.set(e, "generic", g)


KIND_SYSTEMS: dict[str, KindSystem] = {
    "player": _player, "enemy_spawner": _spawner, "weapon_forge": _forge, "heat": _heat,
    "collapse": _collapse, "extract": _extract, "jeeves": _jeeves, "state_store": _vault, "sink": _sink,
}
# Extra access some built-ins need beyond their own components/channels.
_EXTRA_READS: dict[str, tuple[str, ...]] = {"extract": ("stats", "res:outcome")}
_EXTRA_WRITES: dict[str, tuple[str, ...]] = {"enemy_spawner": ("hostile",), "collapse": ("res:outcome",), "extract": ("res:outcome",)}


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
@dataclass
class EcsBuild:
    blueprint: NormalBlueprint
    world: LiveWorld
    scheduler: TickScheduler
    entities: dict[str, int]
    channels: tuple[str, ...]
    systems: tuple[str, ...]
    scripts: dict[str, str] = field(default_factory=dict)

    def step(self, ticks: int = 1):
        return self.scheduler.run(self.world, ticks)

    def component(self, instance_id: str, name: str) -> Any:
        return self.world.get(self.entities[instance_id], name)

    def manifest(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint.blueprint_id,
            "blueprint_fingerprint": self.blueprint.fingerprint(),
            "entities": dict(sorted(self.entities.items())),
            "channels": list(self.channels),
            "systems": list(self.systems),
            "plan_fingerprint": self.scheduler.fingerprint(),
            "scripts": dict(sorted(self.scripts.items())),
        }


def _topo_order(bp: NormalBlueprint) -> list[str]:
    """Nodes ordered so producers precede consumers (cycles keep blueprint order)."""
    order = [n.instance_id for n in bp.nodes]
    deps: dict[str, set[str]] = {i: set() for i in order}
    for w in bp.wires:
        if w.src[0] != w.dst[0]:
            deps[w.dst[0]].add(w.src[0])
    out: list[str] = []
    placed: set[str] = set()
    pending = list(order)
    while pending:
        progressed = False
        for iid in list(pending):
            if deps[iid] <= placed:
                out.append(iid)
                placed.add(iid)
                pending.remove(iid)
                progressed = True
        if not progressed:  # cycle: break deterministically on blueprint order
            iid = pending.pop(0)
            out.append(iid)
            placed.add(iid)
    return out


def _system_name(iid: str) -> str:
    return "bp." + iid.replace("-", "_")


def build_ecs(
    source: Any,
    *,
    seed: int | str = 0,
    scripts: Mapping[str, str | CompiledScript | Mapping[str, Any]] | None = None,
    fixed_dt: float = 1.0 / 60.0,
    strict_access: bool = True,
) -> EcsBuild:
    """Instantiate a blueprint as a runnable ECS world + scheduler.

    ``scripts`` maps an instance id (or a kind, applying to every node of that
    kind) to script source, a compiled script, or ``{"source", "reads",
    "writes"}``.  Script systems run right after their node's built-in system.
    """
    bp = normalize_blueprint(source)
    world = LiveWorld(name=f"bp-{bp.fingerprint()[:16]}", seed=seed)
    world.register_component("node")
    world.register_component("hostile")
    entities: dict[str, int] = {}
    channels: list[str] = []
    for n in bp.nodes:
        spec = KIND_CATALOG.get(n.kind, GENERIC_KIND)
        comps: dict[str, Any] = {"node": {"instance_id": n.instance_id, "kind": n.kind, "config": dict(n.config)}}
        for cname, default in spec.components.items():
            world.register_component(cname)
            overrides = n.config.get(cname) if isinstance(n.config.get(cname), Mapping) else {}
            value = dict(default) if isinstance(default, Mapping) else default
            if isinstance(value, dict):
                value.update({k: v for k, v in overrides.items() if k in value})
            comps[cname] = value
        entities[n.instance_id] = world.spawn(comps)
    for w in bp.wires:
        if w.channel not in channels:
            channels.append(w.channel)
            world.register_event(w.channel)
    world.set_resource("blueprint", {"id": bp.blueprint_id, "fingerprint": bp.fingerprint()})

    scheduler = TickScheduler(strict_access=strict_access, fixed_dt=fixed_dt)
    names: list[str] = []
    attached: dict[str, str] = {}
    producers: dict[str, set[str]] = {}
    for w in bp.wires:
        producers.setdefault(w.dst[0], set()).add(w.src[0])
    order = _topo_order(bp)
    rank = {iid: i for i, iid in enumerate(order)}
    for iid in order:
        n = bp.node(iid)
        spec = KIND_CATALOG.get(n.kind, GENERIC_KIND)
        inputs: dict[str, list[str]] = {}
        for w in bp.inbound(iid):
            inputs.setdefault(w.dst[1], []).append(w.channel)
        outputs = {w.src[1]: w.channel for w in bp.wires if w.src[0] == iid}
        io = NodeIO(iid, {k: tuple(v) for k, v in inputs.items()}, outputs)
        body = KIND_SYSTEMS.get(n.kind, _generic)
        handle = entities[iid]

        def run(ctx: SystemContext, _body: KindSystem = body, _e: int = handle, _io: NodeIO = io) -> None:
            _body(ctx, _e, _io)

        own = tuple(spec.components)
        reads = own + tuple("event:" + c for chans in io.inputs.values() for c in chans) + _EXTRA_READS.get(n.kind, ())
        writes = own + tuple("event:" + c for c in io.outputs.values()) + _EXTRA_WRITES.get(n.kind, ())
        after = tuple(sorted(_system_name(p) for p in producers.get(iid, ()) if p != iid and rank[p] < rank[iid]))
        name = _system_name(iid)
        scheduler.add(SystemDef(name=name, fn=run, reads=reads, writes=writes, after=after))
        names.append(name)
        entry = (scripts or {}).get(iid, (scripts or {}).get(n.kind))
        if entry is not None:
            sname = name + ".script"
            if isinstance(entry, Mapping):
                src = entry.get("source")
                s_reads, s_writes = tuple(entry.get("reads", ())), tuple(entry.get("writes", ()))
            else:
                src, s_reads, s_writes = entry, own, own
            compiled = src if isinstance(src, CompiledScript) else compile_script(str(src), name=sname)
            scheduler.add(script_system(compiled, name=sname, reads=s_reads, writes=s_writes, after=(name,)))
            names.append(sname)
            attached[iid] = compiled.digest
    scheduler.plan()
    return EcsBuild(bp, world, scheduler, entities, tuple(channels), tuple(names), attached)


__all__ = [
    "GENERIC_KIND",
    "KIND_CATALOG",
    "KIND_SYSTEMS",
    "BlueprintAdapterError",
    "EcsBuild",
    "KindSpec",
    "NodeIO",
    "NodeSpec",
    "NormalBlueprint",
    "WireSpec",
    "build_ecs",
    "normalize_blueprint",
]
